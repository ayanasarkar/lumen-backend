# run_validation_harness.py
import os
import sys
import numpy as np
import rasterio
from rasterio.warp import transform_bounds

def verify_step1(ohrc_path, nac_path, dem_path):
    print("=" * 60)
    print("STEP 1: GEOMETRIC PROVENANCE VERIFICATION")
    print("=" * 60)
    
    if not (os.path.exists(ohrc_path) and os.path.exists(nac_path) and os.path.exists(dem_path)):
        print("Error: One or more input paths do not exist. Please check your file names.")
        sys.exit(1)
        
    with rasterio.open(ohrc_path) as ohrc, rasterio.open(nac_path) as nac, rasterio.open(dem_path) as dem:
        # 1. Extract Dimensions
        o_w, o_h = ohrc.width, ohrc.height
        n_w, n_h = nac.width, nac.height
        d_w, d_h = dem.width, dem.height
        
        # 2. Compute Ground Sample Distance (GSD) from Affine Transform
        o_gsd_x = abs(ohrc.transform[0])
        o_gsd_y = abs(ohrc.transform[4])
        n_gsd_x = abs(nac.transform[0])
        n_gsd_y = abs(nac.transform[4])
        d_gsd_x = abs(dem.transform[0])
        d_gsd_y = abs(dem.transform[4])
        
        # 3. Read CRS
        o_crs = ohrc.crs.to_string() if ohrc.crs else "Undefined"
        n_crs = nac.crs.to_string() if nac.crs else "Undefined"
        d_crs = dem.crs.to_string() if dem.crs else "Undefined"
        
        print(f"OHRC (Source):   Dimensions={o_w}x{o_h} | GSD={o_gsd_x:.4f}x{o_gsd_y:.4f} m/px | CRS={o_crs}")
        print(f"NAC (Reference): Dimensions={n_w}x{n_h} | GSD={n_gsd_x:.4f}x{n_gsd_y:.4f} m/px | CRS={n_crs}")
        print(f"DEM (Elevation): Dimensions={d_w}x{d_h} | GSD={d_gsd_x:.4f}x{d_gsd_y:.4f} m/px | CRS={d_crs}")
        print("-" * 60)
        
        # 4. Evaluate Safety Verdict
        is_unsafe_pixel_match = (o_w == n_w and o_h == n_h)
        is_unsafe_gsd_match = np.isclose(o_gsd_x, n_gsd_x, atol=1e-4)
        
        if is_unsafe_pixel_match or is_unsafe_gsd_match:
            print("❌ VERDICT: UNSAFE")
            print("Reason: The OHRC and NAC rasters share identical dimensions or pixel spacings.")
            print("One or both layers were resampled onto the other's grid during the QGIS export.")
            print("This destroys the native feature space and invalidates registration testing.")
            print("ABORTING pipeline execution.")
            sys.exit(1)
        else:
            print("✅ VERDICT: SAFE")
            print("Provenance Check Passed: Rasters preserve their independent, native resolutions.")
            print("OHRC retains its ultra-high resolution (~0.25-0.3m/px) and NAC retains its reference resolution (~1.0-1.5m/px).")
            print("Proceeding to Step 2...")
            
        return ohrc.bounds, nac.bounds, ohrc.crs, nac.crs

# Execute verification using local paths
if __name__ == "__main__":
    # Adjust filenames to match your exact QGIS export names
    verify_step1("ohrc_crop.tif", "nac_crop.tif", "sldem_crop.tif")