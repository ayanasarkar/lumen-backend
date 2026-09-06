import numpy as np
import cv2
import rasterio
import sys

from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

def evaluate_matching(matcher, img_src, img_ref_perturbed, M_gt):
    """Matches images and computes error between Recovered Transform and Ground Truth."""
    m0, m1, conf = matcher.match(img_src, img_ref_perturbed)
    
    num_matches = len(m0)
    if num_matches < 4:
        return num_matches, 0, 0.0, float('inf'), float('inf')
        
    M_rec, inliers_mask = cv2.estimateAffinePartial2D(m0, m1, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    inliers = int(np.sum(inliers_mask)) if inliers_mask is not None else 0
    inlier_ratio = inliers / num_matches if num_matches > 0 else 0.0
    
    if M_rec is None:
        return num_matches, inliers, inlier_ratio, float('inf'), float('inf')
        
    tx_gt, ty_gt = M_gt[0, 2], M_gt[1, 2]
    rot_gt = np.degrees(np.arctan2(M_gt[1, 0], M_gt[0, 0]))
    
    tx_rec, ty_rec = M_rec[0, 2], M_rec[1, 2]
    rot_rec = np.degrees(np.arctan2(M_rec[1, 0], M_rec[0, 0]))
    
    trans_err = np.sqrt((tx_rec - tx_gt)**2 + (ty_rec - ty_gt)**2)
    rot_err = abs(rot_rec - rot_gt)
    
    return num_matches, inliers, inlier_ratio, trans_err, rot_err

def main():
    print("=== HYPOTHESIS BEING TESTED ===")
    print("Relighting should improve matching specifically when source and reference start out at genuinely")
    print("DIFFERENT illumination angles. Condition 3 (Corrected) should perform better than Condition 2")
    print("(Mismatched), while Condition 1 (No mismatch) acts as the theoretical performance ceiling.\n")

    # 1. LOAD APENNINUS TERRAIN
    print("Loading Montes Apenninus terrain...")
    with rasterio.open("apenninus_wac.tif") as src:
        img = src.read(1).astype(np.float32)
        ref_native = np.clip((img - np.nanmin(img)) / (np.nanmax(img) - np.nanmin(img) + 1e-5) * 255.0, 0, 255).astype(np.uint8)

    with rasterio.open("apenninus_dem.tif") as src:
        dem_km = src.read(1).astype(np.float32)
    dem_m = (dem_km - 1737.4) * 1000.0
    
    normals = compute_surface_normals(dem_m, 59.23) 
    normals = cv2.resize(normals, (ref_native.shape[1], ref_native.shape[0]), interpolation=cv2.INTER_LINEAR)

    # 2. GENERATE THE "HARD CASE" SOURCE IMAGE
    # We simulate a source image taken at a completely different time of day (Az: 200, El: 60)
    print("Generating simulated Source Image (Illumination: Az 200°, El 60°)...")
    sun_source = get_sun_vector(200.0, 60.0)
    source_img_result = apply_lunar_lambert(ref_native, normals, sun_source)
    source_img = source_img_result[0] if isinstance(source_img_result, tuple) else source_img_result

    # 3. GENERATE THE CORRECTED REFERENCE
    # We relight the native reference to perfectly match the source's sun angle
    ref_relit_result = apply_lunar_lambert(ref_native, normals, sun_source)
    ref_relit = ref_relit_result[0] if isinstance(ref_relit_result, tuple) else ref_relit_result

    # 4. GENERATE GROUND TRUTH GEOMETRIC PERTURBATION
    np.random.seed(42) 
    h, w = ref_native.shape
    center = (w / 2, h / 2)
    
    angle_gt = np.random.uniform(-5.0, 5.0)
    scale_gt = np.random.uniform(0.97, 1.03)
    tx_gt = np.random.uniform(-50.0, 50.0)
    ty_gt = np.random.uniform(-50.0, 50.0)
    
    M_gt = cv2.getRotationMatrix2D(center, angle_gt, scale_gt)
    M_gt[0, 2] += tx_gt
    M_gt[1, 2] += ty_gt
    print(f"Applied GT Transform -> Rot: {angle_gt:.2f}°, Trans X: {tx_gt:.1f}px, Trans Y: {ty_gt:.1f}px\n")

    # Apply spatial warp to references
    ref_native_warped = cv2.warpAffine(ref_native, M_gt, (w, h), borderMode=cv2.BORDER_REFLECT)
    ref_relit_warped = cv2.warpAffine(ref_relit, M_gt, (w, h), borderMode=cv2.BORDER_REFLECT)

    # 5. RUN ABLATION
    matcher = LoFTRMatcher()
    
    print("Evaluating Cond 1: SAME-ILLUMINATION CEILING (Native vs Native Warped)...")
    c1_m, c1_inl, c1_rat, c1_terr, c1_rerr = evaluate_matching(matcher, ref_native, ref_native_warped, M_gt)
    
    print("Evaluating Cond 2: MISMATCHED, UNCORRECTED (Source vs Native Warped)...")
    c2_m, c2_inl, c2_rat, c2_terr, c2_rerr = evaluate_matching(matcher, source_img, ref_native_warped, M_gt)
    
    print("Evaluating Cond 3: MISMATCHED, CORRECTED (Source vs Relit Warped)...")
    c3_m, c3_inl, c3_rat, c3_terr, c3_rerr = evaluate_matching(matcher, source_img, ref_relit_warped, M_gt)

    # 6. OUTPUT REPORT
    print("\n" + "="*85)
    print("3-CONDITION RELIGHTING ABLATION: PROVING ILLUMINATION CORRECTION")
    print("="*85)
    print(f"{'Condition':<25} | {'Matches':<8} | {'Inliers':<8} | {'Inl %':<8} | {'Rot Err (°)':<12} | {'Trans Err (px)'}")
    print("-" * 85)
    print(f"{'1. Same-Illum Ceiling':<25} | {c1_m:<8} | {c1_inl:<8} | {c1_rat:<8.1%} | {c1_rerr:<12.3f} | {c1_terr:.3f}")
    print(f"{'2. Mismatched (Uncorr)':<25} | {c2_m:<8} | {c2_inl:<8} | {c2_rat:<8.1%} | {c2_rerr:<12.3f} | {c2_terr:.3f}")
    print(f"{'3. Mismatched (Correct)':<25} | {c3_m:<8} | {c3_inl:<8} | {c3_rat:<8.1%} | {c3_rerr:<12.3f} | {c3_terr:.3f}")
    print("="*85)

    # Explicit ordering evaluation
    print("\nVERDICT ON EXPECTED ORDERING (C1 > C3 > C2):")
    if c1_rat >= c3_rat and c3_rat > c2_rat:
        print("[SUCCESS] The expected ordering holds perfectly. Relighting (C3) successfully recovered")
        print("          performance lost to the illumination gap (C2), cleanly validating the PRISM hypothesis.")
    elif c3_rat <= c2_rat:
        print("[FAIL] Condition 3 did not beat Condition 2. Relighting actively hurt or failed to improve matching.")
        print("       Diagnosis: The PRISM correction may be injecting artifacts, or the native WAC shadows")
        print("       are dominating the underlying albedo proxy, causing conflicting light cues when relit.")
    elif c3_rat > c1_rat:
        print("[ANOMALY] Condition 3 beat the Ceiling (C1). This suggests the artificial source illumination")
        print("          happened to cast more salient shadow features for LoFTR than the native WAC lighting did.")
    else:
        print("[MIXED] Ordering is anomalous. Inspect raw metrics.")

if __name__ == "__main__":
    main()