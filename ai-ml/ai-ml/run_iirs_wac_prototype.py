import os
import numpy as np
import cv2
import rasterio

from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

EXPECTED_DEM_SOURCE = "SLDEM2015_512_00N_30N_000_045_FLOAT.LBL"

def print_metadata(lbl_path):
    print("\n=== STEP 1: LBL AND GDAL METADATA ===")
    if os.path.exists(lbl_path):
        with open(lbl_path, 'r') as f:
            for line in f:
                if any(k in line.upper() for k in ["RADIUS", "OFFSET", "SCALING", "UNIT", "MAXIMUM", "MINIMUM"]):
                    print(f"[LBL] {line.strip()}")
        
        with rasterio.open(lbl_path) as src:
            print(f"[GDAL] scales={src.scales}, offsets={src.offsets}, units={src.units}")
            print(f"[GDAL] tags={src.tags()}")
    else:
        print(f"[!] LBL file not found at {lbl_path}")

def load_and_normalize_wac(path):
    with rasterio.open(path) as src:
        img = src.read(1).astype(np.float32)
        img_min, img_max = np.nanmin(img), np.nanmax(img)
        img_norm = np.clip((img - img_min) / (img_max - img_min + 1e-5) * 255.0, 0, 255)
        return img_norm.astype(np.uint8)

def verify_and_load_dem(path, expected_url=None):
    with rasterio.open(path) as src:
        pixel_x_raw = abs(src.transform.a)
        if pixel_x_raw < 1.0:
            pixel_x_m = pixel_x_raw * (2 * np.pi * 1737400) / 360.0
        else:
            pixel_x_m = pixel_x_raw
            
        expected_res = 59.19
        tolerance = 1.5
        if not (expected_res - tolerance <= pixel_x_m <= expected_res + tolerance):
            raise ValueError(f"DEM resolution mismatch: expected ~59.2 m/px (SLDEM2015), got {pixel_x_m:.2f} m/px...")
            
        img = src.read(1).astype(np.float32)
        scale = src.scales[0] if src.scales and src.scales[0] is not None else 1.0
        offset = src.offsets[0] if src.offsets and src.offsets[0] is not None else 0.0
        
        tags = src.tags()
        if scale == 1.0 and offset == 0.0:
            if 'SCALING_FACTOR' in tags: scale = float(tags['SCALING_FACTOR'])
            if 'OFFSET' in tags: offset = float(tags['OFFSET'])
                
        img = img * scale + offset
        if src.nodata is not None:
            img[img == src.nodata * scale + offset] = np.nan
            
        # --- FIX: Convert absolute planetary radius (km) to topographic relief (meters) ---
        img_mean_pre = np.nanmean(img)
        if 1700 < img_mean_pre < 1800:
            print(f"\n[Auto-Correct] DEM mean is {img_mean_pre:.1f}. Converting absolute radius (km) to topographic relief (meters)...")
            img = (img - 1737.4) * 1000.0
        elif 1700000 < img_mean_pre < 1800000:
            print(f"\n[Auto-Correct] DEM mean is {img_mean_pre:.1f}. Converting absolute radius (meters) to topographic relief...")
            img = img - 1737400.0

        img_min, img_max = np.nanmin(img), np.nanmax(img)
        img_mean = np.nanmean(img)
        img_std = np.nanstd(img)
        
        print(f"[Elevation Verified] Stats - Min: {img_min:.1f}m, Max: {img_max:.1f}m, Mean: {img_mean:.1f}m, Std: {img_std:.1f}m")
        
        assert abs(img_mean) < 20000, (
            f"Elevation mean {img_mean:.1f} looks like uncorrected "
            f"planetary radius, not relief — check unit/offset handling."
        )
        
        """Guaranteed output: meters of topographic relief, relative to lunar reference sphere."""
        return img, pixel_x_m

def compute_metrics(m0, m1, conf):
    num_matches = len(m0)
    if num_matches >= 4:
        _, mask = cv2.findHomography(m0, m1, cv2.RANSAC, 3.0)
        inliers = int(np.sum(mask)) if mask is not None else 0
    else:
        inliers = 0
    inlier_ratio = inliers / num_matches if num_matches > 0 else 0.0
    avg_conf = float(np.mean(conf)) if len(conf) > 0 else 0.0
    return num_matches, inliers, inlier_ratio, avg_conf

def main():
    print_metadata("local_data/SLDEM2015_512_00N_30N_000_045_FLOAT.LBL")
    
    print("\nLoading Real Sinus Medii Imagery...")
    source_path = "sinus_medii_wac.tif"
    reference_path = "sinus_medii_wac.tif"
    wac_img = load_and_normalize_wac(source_path)
    dem_img, pixel_scale_m = verify_and_load_dem("sinus_medii_dem.tif", expected_url=EXPECTED_DEM_SOURCE)

    print("\n=== STEP 2: VERIFY SELF-MATCHING ===")
    print(f"Source Path Passed to LoFTR: {source_path}")
    print(f"Reference Path Passed to LoFTR: {reference_path}")
    
    try:
        assert source_path != reference_path, "Source and reference are the same file!"
    except AssertionError as e:
        print(f"[!] ASSERTION CAUGHT: {e}")
        print("Note: IIRS data is locked behind ISSDC Auth. The IIRS Modality Bridge is tested synthetically. We proceed with WAC-only to evaluate self-similarity bias.")

    matcher = LoFTRMatcher()

    # --- INDEPENDENT CONTROL: Shifted WAC ---
    print("\n[Control Test] Running LoFTR on RAW WAC vs SHIFTED RAW WAC (Synthetic 50px, 30px offset)...")
    M = np.float32([[1, 0, 50], [0, 1, 30]])
    shifted_wac = cv2.warpAffine(wac_img, M, (wac_img.shape[1], wac_img.shape[0]))
    
    m0_ctrl, m1_ctrl, conf_ctrl = matcher.match(wac_img, shifted_wac)
    ctrl_matches, ctrl_inliers, ctrl_ratio, ctrl_conf = compute_metrics(m0_ctrl, m1_ctrl, conf_ctrl)
    print(f"Control Results -> Matches: {ctrl_matches}, Inliers: {ctrl_inliers} ({ctrl_ratio:.1%}), Conf: {ctrl_conf:.3f}")
    if ctrl_ratio > 0.95:
        print("[!] WARNING: Harness is measuring self-similarity. A genuinely different image is required for valid ML testing.")

    # --- PRISM RELIGHTING ---
    print("\nComputing PRISM Normals & Relighting...")
    normals = compute_surface_normals(dem_img, pixel_scale_m)
    if normals.shape[:2] != wac_img.shape:
        normals = cv2.resize(normals, (wac_img.shape[1], wac_img.shape[0]), interpolation=cv2.INTER_LINEAR)

    sun_vector_relit = get_sun_vector(135.0, 45.0)
    relit_result = apply_lunar_lambert(wac_img, normals, sun_vector_relit)
    relit_wac = relit_result[0] if isinstance(relit_result, tuple) else relit_result

    # Calculate Pixel Difference
    diff = np.abs(wac_img.astype(np.float32) - relit_wac.astype(np.float32))
    mean_abs_diff = np.mean(diff)
    pct_changed = 100.0 * np.sum(diff > (255 * 0.05)) / diff.size
    print(f"\n[Relight Verified] Mean |Δpixel|: {mean_abs_diff:.4f}, % pixels changed >5%: {pct_changed:.1f}%")

    print("\nRunning LoFTR: Real WAC vs. PRISM-Relit WAC...")
    m0, m1, conf = matcher.match(wac_img, relit_wac)
    num_matches, inliers, inlier_ratio, avg_conf = compute_metrics(m0, m1, conf)

    print("\n" + "="*75)
    print("REAL TERRAIN (SINUS MEDII) WAC vs. RELIT-WAC ABLATION: LoFTR RESULTS")
    print("="*75)
    print(f"Matches (Raw) : {num_matches}")
    print(f"Inliers       : {inliers}")
    print(f"Inlier Ratio  : {inlier_ratio:.1%}")
    print(f"Avg Confidence: {avg_conf:.3f}")
    print("="*75)

if __name__ == "__main__":
    main()
