import numpy as np
import cv2

# Import all the modules we built
from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher
from modality_bridge import bridge_iirs_to_grayscale
from backend_client_stub import get_dem, get_products_for_site, get_spice_kernels

def run_test():
    print("--- Starting Local Pipeline Test ---")
    
    # 1. Initialize Matcher
    matcher = LoFTRMatcher()
    
    # 2. Fetch Mock Data
    site_id = "test_iirs_site" # Let's test the hardest one (Hyperspectral!)
    print(f"\nFetching mock data for site: {site_id}")
    products = get_products_for_site(site_id)
    dem, pixel_scale = get_dem(site_id)
    spice_data = get_spice_kernels(site_id)
    
    # 3. Handle Modality (If it's IIRS, convert 256 bands to Grayscale)
    if products["type"] == "iirs_wac":
        source_image = bridge_iirs_to_grayscale(products["source_cube"])
    else:
        # Mock a source image if it's OHRC
        source_image = np.ones((512, 512), dtype=np.uint8) * 150
        
    ref_image = products["reference_image"]
    
    # 4. Run PRISM Relighting
    print("\nRunning PRISM Relighting...")
    normals = compute_surface_normals(dem, pixel_scale)
    sun_vector = get_sun_vector(spice_data["sun_azimuth"], spice_data["sun_elevation"])
    relit_reference = apply_lunar_lambert(ref_image, normals, sun_vector)
    
    # 5. Run LoFTR Matching
    print("\nRunning LoFTR Matcher...")
    mkpts0, mkpts1, conf = matcher.match(source_image, relit_reference)
    
    print(f"\n✅ TEST SUCCESSFUL!")
    print(f"Matches found: {len(mkpts0)}")
    print(f"Average Confidence: {np.mean(conf) if len(conf) > 0 else 0:.4f}")

if __name__ == "__main__":
    run_test()