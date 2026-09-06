import os
import json
import uuid
import numpy as np
import cv2
import rasterio

# Our custom modules
from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher
from modality_bridge import bridge_iirs_to_grayscale
from backend_client_stub import get_dem, get_products_for_site, get_spice_kernels, register_run_in_db

def load_image_safely(path_or_data):
    """
    Strict loader using rasterio for GeoTIFFs.
    CONTRACT: Always returns EXACTLY one numpy array (H, W). Never a tuple.
    """
    if isinstance(path_or_data, str):
        if not path_or_data or not os.path.exists(path_or_data):
            print(f"[Warning] Path '{path_or_data}' not found. Falling back to synthetic mock array.")
            # BUG 2 FIX: Return ONLY the pixel array, no geotransform tuples attached.
            return np.ones((512, 512), dtype=np.float32) * 150.0
            
        try:
            with rasterio.open(path_or_data) as src:
                # Normal branch: returns ONLY the pixel array
                return src.read(1).astype(np.float32)
        except Exception as e:
            raise IOError(f"[IO Error] rasterio failed to load '{path_or_data}': {e}")
            
    # Safely unpack if an upstream mock accidentally passed a (array, transform) tuple
    if isinstance(path_or_data, tuple):
        path_or_data = path_or_data[0]
        
    if not isinstance(path_or_data, np.ndarray):
        raise TypeError(f"[IO Error] Expected file path string or numpy array, got {type(path_or_data)}")
    
    return path_or_data.astype(np.float32)

def run_pipeline(site_id):
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    print(f"\n🚀 STARTING PIPELINE FOR SITE: {site_id} | RUN ID: {run_id}")
    
    base_dir = f"../data/sites/{site_id}"
    json_dir = os.path.join(base_dir, "matched_points")
    results_dir = os.path.join(base_dir, "results")
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    print("Fetching data (Mock/Real)...")
    products = get_products_for_site(site_id)
    
    # Safe DEM loading
    dem_data = get_dem(site_id)
    if isinstance(dem_data, tuple) and len(dem_data) == 2:
        dem_raw, pixel_scale = dem_data
    else:
        raise ValueError("[Data Error] get_dem() did not return expected (dem, pixel_scale) tuple.")

    spice_data = get_spice_kernels(site_id)

    # Safe Image loading (guaranteed to return arrays, never tuples)
    dem = load_image_safely(dem_raw)
    ref_image = load_image_safely(products.get("reference_image", ""))

    if products.get("type") == "iirs_wac" and "source_cube" in products:
        source_image = bridge_iirs_to_grayscale(products["source_cube"])
    else:
        source_image = load_image_safely(products.get("source_image", ""))
            
    # 5. PRISM Relighting
    print("Running PRISM Relighting...")
    normals = compute_surface_normals(dem, float(pixel_scale)) 
    sun_vector = get_sun_vector(spice_data["sun_azimuth"], spice_data["sun_elevation"])
    
    if dem.shape != ref_image.shape:
        normals = cv2.resize(normals, (ref_image.shape[1], ref_image.shape[0]), interpolation=cv2.INTER_LINEAR)
        
    # FIX: Safely capture the result. If prism.py returns (image, diagnostic_map), grab just the image.
    relit_result = apply_lunar_lambert(ref_image, normals, sun_vector)
    
    if isinstance(relit_result, tuple):
        relit_reference = relit_result[0]
    else:
        relit_reference = relit_result

    # 6. Matching
    print("Running LoFTR...")
    matcher = LoFTRMatcher()
    
    # Passing raw arrays, guaranteed no tuples
    mkpts0, mkpts1, conf = matcher.match(source_image, relit_reference)
    
    matches_list = []
    for i in range(len(mkpts0)):
        matches_list.append({
            "src_x": float(mkpts0[i][0]), "src_y": float(mkpts0[i][1]),
            "ref_x": float(mkpts1[i][0]), "ref_y": float(mkpts1[i][1]),
            "confidence": float(conf[i])
        })
        
    handoff_payload = {
        "site_id": site_id,
        "source_image": "source_mock.cub",
        "reference_image": "reference_mock.cub",
        "matches": matches_list
    }

    json_path = os.path.join(json_dir, f"{run_id}.json")
    relit_path = os.path.join(results_dir, f"{run_id}_relit_reference.tif")
    
    with open(json_path, "w") as f:
        json.dump(handoff_payload, f, indent=2)
    cv2.imwrite(relit_path, relit_reference)
    
    print("\n✅ HANDOFF COMPLETE!")
    register_run_in_db(run_id, site_id, json_path, relit_path)

if __name__ == "__main__":
    run_pipeline("test_ohrc_site")