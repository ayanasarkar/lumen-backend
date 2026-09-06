import os
import numpy as np
import cv2
import rasterio
from rasterio.warp import reproject, Resampling
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

# ===========================================================================
# GEOGRAPHIC ALIGNMENT & DEEP SHADOW MASKING HELPERS
# ===========================================================================

def georeference_align_wac_to_dem(dem_path, raw_wac_path, aligned_wac_output_path):
    """Reprojects raw WAC imagery to match the exact geographic grid of the DEM."""
    with rasterio.open(dem_path) as dem_ds:
        dem_meta = dem_ds.meta.copy()
        dem_transform = dem_ds.transform
        dem_crs = dem_ds.crs
        dem_width = dem_ds.width
        dem_height = dem_ds.height

    with rasterio.open(raw_wac_path) as wac_ds:
        wac_transform = wac_ds.transform
        wac_crs = wac_ds.crs
        aligned_wac_data = np.zeros((dem_height, dem_width), dtype=np.float32)
        
        reproject(
            source=rasterio.band(wac_ds, 1),
            destination=aligned_wac_data,
            src_transform=wac_transform,
            src_crs=wac_crs,
            dst_transform=dem_transform,
            dst_crs=dem_crs,
            resampling=Resampling.bilinear
        )

    dem_meta.update(dtype='float32', count=1)
    with rasterio.open(aligned_wac_output_path, 'w', **dem_meta) as dst_ds:
        dst_ds.write(aligned_wac_data, 1)

    return aligned_wac_data


def stabilized_prism_render(dem, image_B, target_elev, source_elev, azdeg=135.0, cos_threshold=0.05):
    """
    Computes physical illumination correction with float64 precision math,
    clipping/quantizing as the final step, and returns the image + shadow mask.
    """
    normals = compute_surface_normals(dem, 59.23)
    target_sun_vec = get_sun_vector(float(azdeg), float(target_elev))
    source_sun_vec = get_sun_vector(float(azdeg), float(source_elev))

    cos_source_incidence = np.sum(normals * source_sun_vec, axis=-1)
    cos_target_incidence = np.sum(normals * target_sun_vec, axis=-1)

    cos_target_safe = np.clip(cos_target_incidence, 0.0, None)
    cos_source_safe = np.clip(cos_source_incidence, cos_threshold, None)

    ratio = cos_target_safe / cos_source_safe
    print(f"[PRISM] Post-floor ratio range: Min={ratio.min():.4f}, Max={ratio.max():.4f}, Mean={ratio.mean():.4f}")

    # --- 1. DEBUG PRINT BEFORE MATH ---
    h, w = image_B.shape[:2]
    r_slice = slice(min(300, h - 10), min(310, h))
    c_slice = slice(min(300, w - 10), min(310, w))
    print(f"[DEBUG] Source image dtype: {image_B.dtype}, sample unique values in dim patch: {np.unique(image_B[r_slice, c_slice])}")

    # --- 2. FLOAT64 CONVERSION ---
    image_B_float = image_B.astype(np.float64)

    # --- 3. APPLY RATIO IN FLOAT SPACE ---
    relit_float = image_B_float * ratio

    # Unreliable mask denotes pixels under extreme grazing or self-shadowing in source
    unreliable_mask = cos_source_incidence < cos_threshold
    relit_float[unreliable_mask] = 0.0

    # --- 4. CLIP AND QUANTIZE AS THE VERY LAST STEP ---
    pct_clipped = np.mean((relit_float < 0.0) | (relit_float > 255.0)) * 100
    print(f"[PRISM] {pct_clipped:.2f}% of pixels needed output clipping after floor fix")

    relit_clipped = np.clip(relit_float, 0, 255)
    relit_B_shifted = np.round(relit_clipped).astype(np.uint8)

    return relit_B_shifted, unreliable_mask


def run_loftr_raw_output(matcher, source_path_or_arr, ref_path_or_arr):
    """Executes LoFTR and returns matched keypoints alongside the RANSAC inlier mask."""
    try:
        m0, m1, conf = matcher.match(source_path_or_arr, ref_path_or_arr)
    except (TypeError, ValueError):
        im0 = cv2.imread(source_path_or_arr, cv2.IMREAD_GRAYSCALE) if isinstance(source_path_or_arr, str) else source_path_or_arr
        im1 = cv2.imread(ref_path_or_arr, cv2.IMREAD_GRAYSCALE) if isinstance(ref_path_or_arr, str) else ref_path_or_arr
        m0, m1, conf = matcher.match(im0, im1)

    num_matches = len(m0)
    if num_matches >= 4:
        _, mask = cv2.findHomography(m0, m1, cv2.RANSAC, 3.0)
        inlier_mask = mask.ravel().astype(bool) if mask is not None else np.zeros(num_matches, dtype=bool)
    else:
        inlier_mask = np.zeros(num_matches, dtype=bool)

    matches = {
        "m0": m0,
        "m1": m1,
        "conf": conf,
        "num_matches": num_matches
    }
    return matches, inlier_mask


def evaluate_masked_matches(matches, inlier_mask, unreliable_mask):
    """
    Evaluates keypoint inliers across both global and illuminated-only regions,
    filtering points landing in unreliable low-signal shadow zones.
    """
    m1 = matches["m1"]
    num_matches = matches["num_matches"]
    conf = matches["conf"]

    global_inliers = int(np.sum(inlier_mask))
    global_ratio = (global_inliers / num_matches * 100.0) if num_matches > 0 else 0.0
    global_conf = float(np.mean(conf)) if len(conf) > 0 else 0.0

    if num_matches == 0:
        return {
            "inliers": 0,
            "inlier_ratio": 0.0,
            "avg_confidence": 0.0,
            "illuminated_inliers": 0,
            "illuminated_ratio": 0.0,
            "num_matches": 0,
            "illuminated_matches": 0
        }

    h, w = unreliable_mask.shape[:2]
    m1_x = np.clip(np.round(m1[:, 0]).astype(int), 0, w - 1)
    m1_y = np.clip(np.round(m1[:, 1]).astype(int), 0, h - 1)

    in_shadow = unreliable_mask[m1_y, m1_x]
    valid_illum_mask = ~in_shadow

    illuminated_matches = int(np.sum(valid_illum_mask))
    illuminated_inliers = int(np.sum(inlier_mask & valid_illum_mask))
    illuminated_ratio = (illuminated_inliers / illuminated_matches * 100.0) if illuminated_matches > 0 else 0.0

    return {
        "inliers": global_inliers,
        "inlier_ratio": global_ratio,
        "avg_confidence": global_conf,
        "illuminated_inliers": illuminated_inliers,
        "illuminated_ratio": illuminated_ratio,
        "num_matches": num_matches,
        "illuminated_matches": illuminated_matches
    }


def run_synthetic_illumination_ablation(
    dem,
    matcher,
    raw_reference_aligned=None,
    sun_elev_a=60,
    sun_elev_b=20,
    use_synthetic_albedo=True,
    azdeg=135.0
):
    """
    Executes raw vs. relit comparisons using parameters to generate files.
    Enforces rigid shape assertions and supports pure synthetic albedo maps.
    """
    source_path = f"temp_{sun_elev_a}deg_source.tif"
    raw_ref_path = f"temp_{sun_elev_b}deg_raw_reference.tif"
    relit_ref_path = f"temp_{sun_elev_b}_to_{sun_elev_a}deg_relit_reference.tif"

    for path in [source_path, raw_ref_path, relit_ref_path]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                print(f"[Cleanup Warning] Could not remove {path}: {e}")

    if use_synthetic_albedo or raw_reference_aligned is None:
        albedo_mod = np.ones_like(dem, dtype=np.float32) * 0.6
        print(f"[PRISM] Pure Illumination Mode: Generated constant albedo (0.6) with shape {albedo_mod.shape}")
    else:
        albedo_mod = raw_reference_aligned.copy().astype(np.float32)
        if albedo_mod.max() > 1.0:
            albedo_mod /= 255.0

    assert albedo_mod.shape == dem.shape, (
        f"[Alignment Error] albedo_mod shape {albedo_mod.shape} "
        f"must natively match DEM/illumination shape {dem.shape}. "
        f"Check upstream crop/projection parameters."
    )

    # 1. Render targets
    ls_a = LightSource(azdeg=azdeg, altdeg=sun_elev_a)
    img_a_float = ls_a.hillshade(dem, vert_exag=1, dx=1, dy=1)
    img_a = np.clip(img_a_float * albedo_mod * 255.0, 0, 255).astype(np.uint8)
    cv2.imwrite(source_path, img_a)

    ls_b = LightSource(azdeg=azdeg, altdeg=sun_elev_b)
    img_b_float = ls_b.hillshade(dem, vert_exag=1, dx=1, dy=1)
    img_b = np.clip(img_b_float * albedo_mod * 255.0, 0, 255).astype(np.uint8)
    img_b_shifted = np.roll(img_b, shift=(15, 15), axis=(0, 1))
    cv2.imwrite(raw_ref_path, img_b_shifted)

    # 2. Render relit reference AND capture the unreliable shadow mask
    relit_img, unreliable_mask = stabilized_prism_render(
        dem=dem,
        image_B=img_b_shifted,
        target_elev=sun_elev_a,
        source_elev=sun_elev_b,
        azdeg=azdeg
    )
    cv2.imwrite(relit_ref_path, relit_img)

    # 3. Match RAW
    print(f"\nRunning LoFTR: Image A ({sun_elev_a}°) vs Image B ({sun_elev_b}°, RAW)...")
    raw_matches, raw_inliers_mask = run_loftr_raw_output(matcher, source_path, raw_ref_path)
    raw_metrics = evaluate_masked_matches(raw_matches, raw_inliers_mask, unreliable_mask)

    # 4. Match RELIT
    print(f"Running LoFTR: Image A ({sun_elev_a}°) vs Image B (PRISM-Relit {sun_elev_b}° -> {sun_elev_a}°)...")
    relit_matches, relit_inliers_mask = run_loftr_raw_output(matcher, source_path, relit_ref_path)
    relit_metrics = evaluate_masked_matches(relit_matches, relit_inliers_mask, unreliable_mask)

    return raw_metrics, relit_metrics, unreliable_mask


def main():
    print("=== LOADING MONTES APENNINUS ===")

    dem_path = "apenninus_dem.tif"
    raw_wac_path = "apenninus_wac.tif"
    aligned_wac_path = "aligned_apenninus_wac.tif"

    with rasterio.open(dem_path) as src:
        dem_km = src.read(1).astype(np.float32)

    montes_apenninus_dem = (dem_km - 1737.4) * 1000.0

    # 1. Align the WAC image geographically to the DEM raster
    raw_reference_aligned = georeference_align_wac_to_dem(
        dem_path=dem_path,
        raw_wac_path=raw_wac_path,
        aligned_wac_output_path=aligned_wac_path
    )

    # Normalize aligned WAC array to 8-bit dynamic range
    wac_min, wac_max = np.nanmin(raw_reference_aligned), np.nanmax(raw_reference_aligned)
    raw_reference_aligned = np.clip(
        (raw_reference_aligned - wac_min) / (wac_max - wac_min + 1e-5) * 255.0, 0, 255
    ).astype(np.uint8)

    # 2. ENFORCE STABILIZATION ASSERTION
    print(f"[Trace] Raw SLDEM2015 Shape       : {montes_apenninus_dem.shape}")
    print(f"[Trace] Aligned WAC Albedo Shape : {raw_reference_aligned.shape}")
    assert raw_reference_aligned.shape == montes_apenninus_dem.shape, (
        f"[Alignment Error] Reference shape {raw_reference_aligned.shape} must match "
        f"DEM shape {montes_apenninus_dem.shape} natively."
    )

    matcher = LoFTRMatcher()

    # ===========================================================================
    # STABILIZED EVALUATION SWEEP WITH DEEP-SHADOW ISOLATION
    # ===========================================================================
    gaps = [20, 10, 5]
    results_table = []

    for gap_angle in gaps:
        print(f"\n===========================================================================")
        print(f"EVALUATING GAP: 60° (Target) vs {gap_angle}° (Source)")
        print(f"===========================================================================")

        raw_metrics, relit_metrics, shadow_mask = run_synthetic_illumination_ablation(
            dem=montes_apenninus_dem,
            matcher=matcher,
            raw_reference_aligned=raw_reference_aligned,
            sun_elev_a=60,
            sun_elev_b=gap_angle,
            use_synthetic_albedo=True
        )

        shadow_pct = np.mean(shadow_mask) * 100.0

        results_table.append({
            "gap": f"60° vs {gap_angle}°",
            "shadow_pct": shadow_pct,
            "raw_inliers": raw_metrics["inliers"],
            "raw_ratio": raw_metrics["inlier_ratio"],
            "raw_conf": raw_metrics["avg_confidence"],
            "relit_inliers": relit_metrics["inliers"],
            "relit_ratio": relit_metrics["inlier_ratio"],
            "relit_conf": relit_metrics["avg_confidence"],
            "relit_illum_inliers": relit_metrics["illuminated_inliers"],
            "relit_illum_ratio": relit_metrics["illuminated_ratio"]
        })

    print("\n" + "=" * 100)
    print("FINAL ILLUMINATION ROBUSTNESS SUMMARY (WITH DEEP-SHADOW ISOLATION)")
    print("=" * 100)
    print(f"{'Gap Setup':<12} | {'Shadow %':<8} | {'Raw (All)':<20} | {'Relit (All)':<20} | {'Relit (Sunlit-Only)':<20}")
    print("-" * 100)

    for row in results_table:
        raw_str = f"{row['raw_inliers']} ({row['raw_ratio']:.1f}%)"
        relit_str = f"{row['relit_inliers']} ({row['relit_ratio']:.1f}%)"
        illum_str = f"{row['relit_illum_inliers']} ({row['relit_illum_ratio']:.1f}%)"
        print(f"{row['gap']:<12} | {row['shadow_pct']:>6.1f}%  | {raw_str:<20} | {relit_str:<20} | {illum_str:<20}")

    print("=" * 100)


if __name__ == "__main__":
    main()