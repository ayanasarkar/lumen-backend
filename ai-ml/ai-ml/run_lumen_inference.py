import os
import json
import uuid
import rasterio
import numpy as np
import torch
from datetime import datetime

# Import existing validated math and matching logic
from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

# Import Backend A's designated client library functions ONLY
from backend_client_stub import get_products_for_site, get_dem, get_spice_kernels

# ---------------------------------------------------------
# TASK 2.3: HARDENING - IDEMPOTENCY
# Seed randomness to guarantee identical outputs on re-runs
# ---------------------------------------------------------
torch.manual_seed(42)
np.random.seed(42)

def safe_fetch_backend_data(site_id):
    """Wraps Backend A calls to fail loudly on missing or malformed data."""
    print(f"[{site_id}] Fetching data from Backend A...")
    
    try:
        products = get_products_for_site(site_id)
        if not products or 'source_image_path' not in products or 'reference_image_path' not in products:
            raise ValueError(f"Backend A returned malformed products payload for {site_id}.")
            
        dem_path, pixel_scale = get_dem(site_id)
        if not dem_path or not os.path.exists(dem_path):
            raise FileNotFoundError(f"Backend A failed to provide a valid DEM for {site_id}.")
            
        spice = get_spice_kernels(site_id)
        if 'sun_azimuth' not in spice or 'sun_elevation' not in spice:
            raise ValueError(f"Backend A returned incomplete SPICE geometry for {site_id}.")
            
        return products, dem_path, pixel_scale, spice
        
    except Exception as e:
        raise RuntimeError(f"🚨 FATAL: Backend A data fetch failed for {site_id}: {str(e)}")

def check_coordinate_space(src_profile, ref_profile, site_id):
    """
    TASK 1.3: Verifies if the matched coordinates will be in raw pixel space or calibrated space.
    """
    is_src_raw = src_profile['transform'].is_identity
    is_ref_raw = ref_profile['transform'].is_identity
    
    space_status = "RAW PIXEL SPACE" if (is_src_raw and is_ref_raw) else "CALIBRATED .CUB SPACE"
    print(f"\n🔍 COORDINATE SPACE VERIFICATION ({site_id}):")
    print(f"  -> Detected coordinate space: {space_status}")
    print("  -> (This space must match Backend B's TerraLock expectations)\n")
    return space_status

def run_pipeline(site_id):
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    print(f"\n🚀 STARTING LUMEN PIPELINE | SITE: {site_id} | RUN: {run_id}")
    
    # 1. Fetch real data safely
    products, dem_path, pixel_scale, spice = safe_fetch_backend_data(site_id)
    
    # 2. Load images via Rasterio to preserve metadata
    with rasterio.open(products['source_image_path']) as src_data:
        source_image = src_data.read(1)
        src_profile = src_data.profile
        
    with rasterio.open(products['reference_image_path']) as ref_data:
        ref_image = ref_data.read(1)
        ref_profile = ref_data.profile
        
    with rasterio.open(dem_path) as dem_data:
        dem_array = dem_data.read(1)
        
    # Log coordinate space
    check_coordinate_space(src_profile, ref_profile, site_id)

    # ---------------------------------------------------------
    # TASK 2.2: HARDENING - DEM NaN/NoData GAP HANDLING
    # ---------------------------------------------------------
    print("Running PRISM Relighting...")
    normals = compute_surface_normals(dem_array, pixel_scale)
    sun_vector = get_sun_vector(spice["sun_azimuth"], spice["sun_elevation"])
    relit_reference = apply_lunar_lambert(ref_image, normals, sun_vector)
    
    # ---------------------------------------------------------
    # TASK 2.1: HARDENING - POLAR SHADOW / UNMATCHABLE REGION
    # ---------------------------------------------------------
    # If the relit image is almost entirely black (near-total shadow), abort early.
    if np.nanmean(relit_reference) < 5.0:
        raise RuntimeError(f"🚨 ABORT: Site {site_id} is in near-total shadow. Aborting to prevent silent high-confidence garbage matches.")

    print("Running LoFTR Matching...")
    matcher = LoFTRMatcher()
    mkpts0, mkpts1, conf = matcher.match(source_image, relit_reference)
    
    # 3. Format Handoff JSON (TASK 3.1)
    matches_list = [
        {
            "src_x": float(mkpts0[i][0]),
            "src_y": float(mkpts0[i][1]),
            "ref_x": float(mkpts1[i][0]),
            "ref_y": float(mkpts1[i][1]),
            "confidence": float(conf[i])
        }
        for i in range(len(mkpts0))
    ]
        
    handoff_payload = {
        "site_id": site_id,
        "source_image": os.path.basename(products['source_image_path']),
        "reference_image": os.path.basename(products['reference_image_path']),
        "matches": matches_list
    }

    # 4. Define Paths & Write Files (TASK 3.2 & 3.3)
    base_dir = f"../data/sites/{site_id}"
    os.makedirs(os.path.join(base_dir, "matched_points"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "results"), exist_ok=True)
    
    json_path = os.path.join(base_dir, "matched_points", f"{run_id}.json")
    relit_path = os.path.join(base_dir, "results", f"{run_id}_relit_reference.tif")
    
    with open(json_path, "w") as f:
        json.dump(handoff_payload, f, indent=2)
        
    ref_profile.update(dtype=relit_reference.dtype, compress='lzw')
    with rasterio.open(relit_path, 'w', **ref_profile) as dst:
        dst.write(relit_reference, 1)
        
    # 5. Internal Sanity Check Logging (TASK 3.5)
    internal_log_path = f"internal_match_quality_{run_id}.log"
    with open(internal_log_path, "w") as log:
        log.write(f"INTERNAL ONLY - NOT OFFICIAL MATCHMETRICS RESULT\n")
        log.write(f"Run ID: {run_id}\nTimestamp: {datetime.now().isoformat()}\n")
        log.write(f"Total raw matches: {len(matches_list)}\n")
        if len(conf) > 0:
            log.write(f"Mean Confidence: {np.mean(conf):.4f}\n")
            log.write(f"Max Confidence: {np.max(conf):.4f}\n")
            
    print(f"\n✅ HANDOFF COMPLETE!")
    print(f"  -> JSON: {json_path}")
    print(f"  -> Relit Image: {relit_path}")
    print(f"  -> Internal Log: {internal_log_path}")

if __name__ == "__main__":
    # Test on one equatorial site first
    run_pipeline("test_equatorial_site_01")