import os
import sys
import json
import numpy as np
import cv2
import rasterio
import torch
from match_loftr import LoFTRMatcher
from prism import (
    compute_surface_normals,
    get_sun_vector,
    apply_lunar_lambert
)
from backend_client_stub import get_products_for_site, get_dem, get_spice_kernels

MIN_RANSAC_INLIERS = 6
RANSAC_REPROJ_THRESH = 3.0

def compute_local_contrast(image, patch_size=16):
    h, w = image.shape[:2]
    h_trim = (h // patch_size) * patch_size
    w_trim = (w // patch_size) * patch_size
    trimmed = image[:h_trim, :w_trim]
    patches = trimmed.reshape(h_trim // patch_size, patch_size, w_trim // patch_size, patch_size)
    patch_stds = np.std(patches, axis=(1, 3))
    return float(np.mean(patch_stds))

def compute_spatial_bounding_box_coverage(pts, img_shape):
    if len(pts) < 2:
        return 0.0
    x_min, y_min = np.min(pts, axis=0)
    x_max, y_max = np.max(pts, axis=0)
    bbox_area = max(0, x_max - x_min) * max(0, y_max - y_min)
    total_area = img_shape[0] * img_shape[1]
    return float((bbox_area / total_area) * 100.0)

def run_evaluation(site_id):
    torch.manual_seed(42)
    np.random.seed(42)
    
    print("=" * 70)
    print(f"LUMEN REAL-DATA BENCHMARK & ABLATION: {site_id}")
    print("=" * 70)

    # 1. Ingest Data
    products = get_products_for_site(site_id)
    dem_path, dem_pixel_scale = get_dem(site_id)
    spice = get_spice_kernels(site_id)

    ohrc_path = products.get('source_image_path') or products.get('source_image')
    nac_path = products.get('reference_image_path') or products.get('reference_image')

    def load_tif(filepath):
        if not os.path.exists(filepath):
            print(f"[!] ERROR: Missing file {filepath}")
            sys.exit(1)
        with rasterio.open(filepath) as src:
            return src.read(1).astype(np.float32)

    ohrc_img = load_tif(ohrc_path)
    nac_img = load_tif(nac_path)
    dem_img = load_tif(dem_path)

    # Retrieve native resolutions using rasterio
    with rasterio.open(ohrc_path) as src:
        src_res = src.res[0]
    with rasterio.open(nac_path) as ref:
        ref_res = ref.res[0]
    with rasterio.open(dem_path) as dem_file:
        dem_res = dem_file.res[0]

    res_ratio = dem_res / src_res

    print("\n[STEP 1: MULTI-RESOLUTION RATIO AUDIT]")
    print(f"  -> OHRC Source Native Pixel Scale : {src_res:.4f} m/px ({ohrc_img.shape[1]}x{ohrc_img.shape[0]} px)")
    print(f"  -> LRO NAC Reference Pixel Scale  : {ref_res:.4f} m/px ({nac_img.shape[1]}x{nac_img.shape[0]} px)")
    print(f"  -> SLDEM2015 Native Pixel Scale   : {dem_res:.1f} m/px ({dem_img.shape[1]}x{dem_img.shape[0]} cells)")
    print(f"  -> DEM to OHRC Resolution Ratio   : {res_ratio:.1f}x Resolution Disparity")

    # 2. PRISM Physical Relighting
    normals = compute_surface_normals(dem_img, dem_pixel_scale)
    src_az = spice['source_sun_azimuth']
    src_el = spice['source_sun_elevation']
    ref_az = spice['ref_sun_azimuth']
    ref_el = spice['ref_sun_elevation']

    src_sun_vec = get_sun_vector(src_az, src_el)
    ref_sun_vec = get_sun_vector(ref_az, ref_el)

    relit_ref_img, smooth_corr, meta = apply_lunar_lambert(
        nac_img, normals, src_sun_vec, ref_sun_vec
    )

    # 3. Radiometric Sanity Diagnostics
    raw_min, raw_max = int(np.min(nac_img)), int(np.max(nac_img))
    relit_min, relit_max = int(np.min(relit_ref_img)), int(np.max(relit_ref_img))
    raw_global_std = float(np.std(nac_img))
    relit_global_std = float(np.std(relit_ref_img))
    raw_local_std = compute_local_contrast(nac_img)
    relit_local_std = compute_local_contrast(relit_ref_img)

    print("\n[STEP 3: RADIOMETRIC & DYNAMIC RANGE AUDIT]")
    print(f"  -> RAW REF   | Range: [{raw_min:3d}, {raw_max:3d}] | Global Std: {raw_global_std:5.2f} | Local Patch Std: {raw_local_std:5.2f}")
    print(f"  -> RELIT REF | Range: [{relit_min:3d}, {relit_max:3d}] | Global Std: {relit_global_std:5.2f} | Local Patch Std: {relit_local_std:5.2f}")
    print(f"  -> Std Deviation Ratio (Relit / Raw): {relit_global_std / raw_global_std:.2f}x (Target: ~1.0x to 1.5x)")

    # Save visual verification side-by-side
    diag_dir = "diagnostic_crops"
    os.makedirs(diag_dir, exist_ok=True)
    comparison_panel = np.hstack([
        ohrc_img[:512, :512],
        nac_img[:512, :512],
        relit_ref_img[:512, :512]
    ])
    cv2.imwrite(os.path.join(diag_dir, "real_site_ablation_side_by_side.png"), comparison_panel)
    print(f"  -> Saved Visual Panel to: {diag_dir}/real_site_ablation_side_by_side.png [Source | Raw Ref | Relit Ref]")

    # 4. Feature Matching
    matcher = LoFTRMatcher()
    print("\n[LoFTR] Matching Source (OHRC) vs RAW Reference (NAC)...")
    mkpts0_raw, mkpts1_raw, conf_raw = matcher.match(ohrc_img, nac_img)
    
    print("\n[LoFTR] Matching Source (OHRC) vs PRISM-RELIT Reference (NAC)...")
    mkpts0_relit, mkpts1_relit, conf_relit = matcher.match(ohrc_img, relit_ref_img)

    # 5. RANSAC Fitting & Spatial Distribution
    def fit_transform(pts0, pts1):
        if len(pts0) < 4:
            return 0, 0.0, None, None
        H, mask = cv2.findHomography(pts0, pts1, cv2.RANSAC, RANSAC_REPROJ_THRESH)
        inliers = int(np.sum(mask)) if mask is not None else 0
        ratio = inliers / len(pts0) if len(pts0) > 0 else 0.0
        return inliers, ratio, H, mask

    inliers_raw, ratio_raw, H_raw, mask_raw = fit_transform(mkpts0_raw, mkpts1_raw)
    inliers_relit, ratio_relit, H_relit, mask_relit = fit_transform(mkpts0_relit, mkpts1_relit)

    cov_raw = compute_spatial_bounding_box_coverage(mkpts1_raw, nac_img.shape)
    cov_relit = compute_spatial_bounding_box_coverage(mkpts1_relit, relit_ref_img.shape)

    # 6. Checkpoints & RMSE Evaluation
    gt_path = "ground_truth_points.json"
    gt_data = []
    if os.path.exists(gt_path):
        with open(gt_path, "r") as f:
            gt_data = json.load(f).get(site_id, [])

    def evaluate_metrics(H, inliers, pts0, pts1, gt_points, label):
        print(f"\n--- Ground Truth Breakdown: {label} ---")
        if not gt_points:
            print("  No ground truth points provided.")
            return "N/A", "N/A"

        nn_residuals = []
        for idx, pt in enumerate(gt_points):
            src_target = np.array(pt["src_pt"])
            ref_target = np.array(pt["ref_pt"])
            if len(pts0) > 0:
                dists = np.linalg.norm(pts0 - src_target, axis=1)
                nearest_idx = np.argmin(dists)
                pred_ref = pts1[nearest_idx]
                err = np.linalg.norm(pred_ref - ref_target)
            else:
                err = np.nan
            nn_residuals.append(err)
            pt_name = pt.get('name', f"Point {idx+1}")
            print(f"  {pt_name:20s} {pt['src_pt']} -> Nearest Match Dist: {err:.3f} px")

        valid_nn = [e for e in nn_residuals if not np.isnan(e)]
        mean_nn_dist = np.sqrt(np.mean(np.array(valid_nn)**2)) if valid_nn else np.nan

        if H is None or inliers < MIN_RANSAC_INLIERS:
            h_rmse_str = f"FAILED ({inliers} inliers, min {MIN_RANSAC_INLIERS} req)"
            print(f"  [WARNING] RANSAC Transform Diverged: {h_rmse_str}")
        else:
            h_errors = []
            for idx, pt in enumerate(gt_points):
                src_homo = np.array([pt["src_pt"][0], pt["src_pt"][1], 1.0])
                pred = H @ src_homo
                if pred[2] == 0:
                    err = np.nan
                else:
                    pred_xy = pred[:2] / pred[2]
                    err = np.linalg.norm(pred_xy - np.array(pt["ref_pt"]))
                h_errors.append(err)
                pt_name = pt.get('name', f"Point {idx+1}")
                print(f"  {pt_name:20s} {pt['src_pt']} -> H-Projected Reprojection Error: {err:.3f} px")
            valid_h = [e for e in h_errors if not np.isnan(e)]
            h_rmse = np.sqrt(np.mean(np.array(valid_h)**2)) if valid_h else np.nan
            h_rmse_str = f"{h_rmse:.3f} px"

        return h_rmse_str, f"{mean_nn_dist:.3f} px"

    h_rmse_raw, nn_raw = evaluate_metrics(H_raw, inliers_raw, mkpts0_raw, mkpts1_raw, gt_data, "RAW PAIR")
    h_rmse_relit, nn_relit = evaluate_metrics(H_relit, inliers_relit, mkpts0_relit, mkpts1_relit, gt_data, "RELIT PAIR")

    print("\n" + "=" * 70)
    print("REAL LUNAR DATASET ABLATION SUMMARY TABLE")
    print("=" * 70)
    print(f"PAIR        | MATCHES | INLIERS (%) | MEAN CONF | H-PROJECTED RMSE | NEAREST RESIDUAL | BBOX COV")
    print(f"RAW PAIR    | {len(mkpts0_raw):7d} | {inliers_raw:2d} ({ratio_raw*100:4.1f}%) | {np.mean(conf_raw) if len(conf_raw)>0 else 0:9.3f} | {h_rmse_raw:18s} | {nn_raw:16s} | {cov_raw:.1f}%")
    print(f"RELIT PAIR  | {len(mkpts0_relit):7d} | {inliers_relit:2d} ({ratio_relit*100:4.1f}%) | {np.mean(conf_relit) if len(conf_relit)>0 else 0:9.3f} | {h_rmse_relit:18s} | {nn_relit:16s} | {cov_relit:.1f}%")
    print("=" * 70)

if __name__ == "__main__":
    run_evaluation("real_equatorial_crater_01")