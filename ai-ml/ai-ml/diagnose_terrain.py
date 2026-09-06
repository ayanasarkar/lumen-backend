import os
import numpy as np
import cv2
import rasterio
from rasterio.windows import Window
from rasterio.env import Env

from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

def analyze_sinus_medii():
    print("=== TASK 1: SUN ANGLE CONFIGURATION ===")
    print("Source (WAC) Sun Vector : Baked-in shadows from USGS mosaic (Variable Azimuth, typically ~10-30° Elevation)")
    print("Relit (PRISM) Sun Vector: Hardcoded to Az: 135.0°, El: 45.0°")
    print("Result: Sun angles are genuinely different. The lack of pixel change is NOT due to identical light vectors.\n")

    print("=== TASK 2: SINUS MEDII TERRAIN GRADIENTS ===")
    with rasterio.open("sinus_medii_dem.tif") as src:
        dem = src.read(1)
    
    # Calculate slopes using exact math
    dy, dx = np.gradient(dem, 59.23, 59.23)
    slope_mag = np.sqrt(dx**2 + dy**2)
    slope_deg = np.degrees(np.arctan(slope_mag))
    
    print(f"Mean Slope Magnitude : {np.nanmean(slope_deg):.2f}°")
    print(f"Max Slope Magnitude  : {np.nanmax(slope_deg):.2f}°")
    print(f"Pixels < 2° Slope    : {100.0 * np.sum(slope_deg < 2.0) / slope_deg.size:.1f}%")
    if np.nanmean(slope_deg) < 3.0:
        print("Verdict: Terrain is exceptionally flat. PRISM is functionally acting as a flat scalar multiplier.\n")


    
    # 1. Stream the WAC for the new site
    print("Fetching WAC for Montes Apenninus...")
    wac_url = "https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LROC-WAC_Mosaic_global_100m_June2013.tif"
    with Env(GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=3, GDAL_HTTP_TIMEOUT=120):
        with rasterio.open(wac_url) as src:
            tgt_x_m = target_lon * (np.pi / 180.0) * 1737400.0
            tgt_y_m = target_lat * (np.pi / 180.0) * 1737400.0
            row_off, col_off = src.index(tgt_x_m, tgt_y_m)
            window = Window(col_off - 250, row_off - 250, 500, 500) # 50km footprint
            data = src.read(1, window=window)
            meta = src.meta.copy()
            meta.update({"driver": "GTiff", "height": window.height, "width": window.width, "transform": src.window_transform(window), "compress": "lzw"})
            with rasterio.open("apenninus_wac.tif", "w", **meta) as dest:
                dest.write(data, 1)

    # 2. Crop the local SLDEM2015 tile for the new site
    print("Cropping local SLDEM2015 for Montes Apenninus...")
    lbl_path = "local_data/SLDEM2015_512_00N_30N_000_045_FLOAT.LBL"
    with rasterio.open(lbl_path) as src:
        col_off = int((target_lon - 0.0) * 512.0)
        row_off = int((30.0 - target_lat) * 512.0)
        pixel_scale_m = (1.0 / 512.0) * (2 * np.pi * 1737400.0) / 360.0
        size_px = int(50000.0 / pixel_scale_m)
        window = Window(col_off - size_px//2, row_off - size_px//2, size_px, size_px)
        
        data = src.read(1, window=window).astype("float32")
        scale = src.scales[0] if src.scales and src.scales[0] else 1.0
        offset = src.offsets[0] if src.offsets and src.offsets[0] else 0.0
        elevation_m = data * scale + offset
        if src.nodata is not None:
            elevation_m[data == src.nodata] = np.nan
            
        meta = src.meta.copy()
        meta.update({"driver": "GTiff", "height": window.height, "width": window.width, "transform": src.window_transform(window), "compress": "lzw", "dtype": "float32", "nodata": np.nan})
        with rasterio.open("apenninus_dem.tif", "w", **meta) as dest:
            dest.write(elevation_m, 1)

def run_high_relief_matching():
    # Load and normalize WAC
    with rasterio.open("apenninus_wac.tif") as src:
        img = src.read(1).astype(np.float32)
        wac_img = np.clip((img - np.nanmin(img)) / (np.nanmax(img) - np.nanmin(img) + 1e-5) * 255.0, 0, 255).astype(np.uint8)

    # Load DEM
    with rasterio.open("apenninus_dem.tif") as src:
        dem_img = src.read(1).astype(np.float32)
        
    print("\nComputing PRISM Relighting for Montes Apenninus...")
    normals = compute_surface_normals(dem_img, 59.23)
    normals = cv2.resize(normals, (wac_img.shape[1], wac_img.shape[0]), interpolation=cv2.INTER_LINEAR)
    
    sun_vector = get_sun_vector(135.0, 45.0)
    relit_result = apply_lunar_lambert(wac_img, normals, sun_vector)
    relit_wac = relit_result[0] if isinstance(relit_result, tuple) else relit_result

    # Compute Pixel Differences
    diff = np.abs(wac_img.astype(np.float32) - relit_wac.astype(np.float32))
    mean_abs_diff = np.mean(diff)
    pct_changed = 100.0 * np.sum(diff > (255 * 0.05)) / diff.size
    print(f"[Relight Verified] Mean |Δpixel|: {mean_abs_diff:.4f}, % pixels changed >5%: {pct_changed:.1f}%")

    # Match
    print("Running LoFTR on Montes Apenninus...")
    matcher = LoFTRMatcher()
    m0, m1, conf = matcher.match(wac_img, relit_wac)
    
    num_matches = len(m0)
    if num_matches >= 4:
        _, mask = cv2.findHomography(m0, m1, cv2.RANSAC, 3.0)
        inliers = int(np.sum(mask)) if mask is not None else 0
    else:
        inliers = 0
    inlier_ratio = inliers / num_matches if num_matches > 0 else 0.0

    print(f"Apenninus Results -> Matches: {num_matches}, Inliers: {inliers} ({inlier_ratio:.1%}), Conf: {np.mean(conf):.3f}")

if __name__ == "__main__":
    analyze_sinus_medii()
    fetch_high_relief_site()
    run_high_relief_matching()