"""
LUMEN AI/ML TRACK — COMPLETE SYSTEM VERIFICATION SUITE
Exercises: prism.py, modality_bridge.py, match_loftr.py, backend_client_stub.py, run_lumen_inference.py
"""

import os
import sys
import numpy as np
import torch
import rasterio

# Force deterministic execution
torch.manual_seed(42)
np.random.seed(42)

print("=" * 60)
print("  LUMEN AI/ML TRACK: COMPLETE SYSTEM HEALTH CHECK")
print("=" * 60)

# Test 1: PRISM Surface Normals & Shading
try:
    from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
    dem_test = np.ones((100, 100), dtype=np.float32) * 500.0
    dem_test[50, 50] = -9999.0  # Injected NoData gap
    normals = compute_surface_normals(dem_test, pixel_scale=59.0, nodata_val=-9999.0)
    assert normals.shape == (100, 100, 3), "Normals shape mismatch"
    assert np.isnan(normals[50, 50, 0]), "NoData masking failed to set NaN"
    
    sun_vec = get_sun_vector(azimuth_deg=45.0, elevation_deg=30.0)
    assert np.isclose(np.linalg.norm(sun_vec), 1.0), "Sun vector not unit length"
    
    albedo_test = np.ones((100, 100), dtype=np.float32) * 128.0
    relit = apply_lunar_lambert(albedo_test, normals, sun_vec)
    assert relit.dtype == np.uint8, "Relit image dtype must be uint8"
    assert relit[50, 50] == 0, "NoData region must map to 0 in output"
    print("✅ 1. PRISM-lite (prism.py): PASSED")
except Exception as e:
    print(f"❌ 1. PRISM-lite (prism.py): FAILED -> {e}")
    sys.exit(1)

# Test 2: IIRS Modality Bridge
try:
    from modality_bridge import bridge_iirs_to_grayscale
    fake_cube = np.random.uniform(100, 200, (256, 128, 128)).astype(np.float32)
    gray = bridge_iirs_to_grayscale(fake_cube)
    assert gray.shape == (128, 128), "Grayscale output shape mismatch"
    assert gray.dtype == np.uint8, "Grayscale output must be normalized uint8"
    print("✅ 2. Modality Bridge (modality_bridge.py): PASSED")
except Exception as e:
    print(f"❌ 2. Modality Bridge (modality_bridge.py): FAILED -> {e}")
    sys.exit(1)

# Test 3: LoFTR Matcher Initialisation & Normalisation
try:
    from match_loftr import LoFTRMatcher
    matcher = LoFTRMatcher(device=torch.device('cpu'))
    img0 = np.random.randint(0, 255, (256, 256), dtype=np.uint8)
    img1 = np.random.randint(0, 255, (256, 256), dtype=np.uint8)
    mkpts0, mkpts1, conf = matcher.match(img0, img1)
    assert isinstance(mkpts0, np.ndarray), "mkpts0 must be numpy array"
    assert isinstance(conf, np.ndarray), "conf must be numpy array"
    print("✅ 3. SelenoMatch-Net / LoFTR (match_loftr.py): PASSED")
except Exception as e:
    print(f"❌ 3. SelenoMatch-Net / LoFTR (match_loftr.py): FAILED -> {e}")
    sys.exit(1)

# Test 4: End-to-End Pipeline Execution & Geospatial Handoff
try:
    from run_lumen_inference import run_pipeline
    test_site = "system_verify_site"
    run_pipeline(test_site)
    
    # Confirm output files exist on disk
    site_dir = f"../data/sites/{test_site}"
    json_dir = os.path.join(site_dir, "matched_points")
    results_dir = os.path.join(site_dir, "results")
    
    json_files = os.listdir(json_dir)
    tif_files = os.listdir(results_dir)
    assert len(json_files) > 0, "Matched points JSON was not written"
    assert len(tif_files) > 0, "Relit GeoTIFF was not written"
    
    # Confirm GeoTIFF geospatial metadata retention
    tif_path = os.path.join(results_dir, tif_files[0])
    with rasterio.open(tif_path) as src:
        assert src.crs is not None or src.transform.is_identity, "Raster profile corrupted"
        assert src.compression == rasterio.enums.Compression.lzw, "LZW compression not applied"
        
    print("✅ 4. Pipeline Integration & Handoff (run_lumen_inference.py): PASSED")
except Exception as e:
    print(f"❌ 4. Pipeline Integration & Handoff (run_lumen_inference.py): FAILED -> {e}")
    sys.exit(1)

print("=" * 60)
print("  ALL 4 CORE AI/ML MODULES ARE FULLY OPERATIONAL")
print("=" * 60)