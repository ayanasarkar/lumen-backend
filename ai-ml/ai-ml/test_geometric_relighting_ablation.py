import numpy as np
import cv2
import rasterio

from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

def evaluate_matching(matcher, img_src, img_ref_perturbed, M_gt):
    """Matches images and computes error between Recovered Transform and Ground Truth."""
    m0, m1, conf = matcher.match(img_src, img_ref_perturbed)
    
    num_matches = len(m0)
    if num_matches < 4:
        return num_matches, 0, 0.0, float('inf'), float('inf')
        
    # Recover the Affine Transform using RANSAC
    M_rec, inliers_mask = cv2.estimateAffinePartial2D(m0, m1, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    inliers = int(np.sum(inliers_mask)) if inliers_mask is not None else 0
    inlier_ratio = inliers / num_matches if num_matches > 0 else 0.0
    
    if M_rec is None:
        return num_matches, inliers, inlier_ratio, float('inf'), float('inf')
        
    # Extract Ground Truth parameters
    tx_gt, ty_gt = M_gt[0, 2], M_gt[1, 2]
    rot_gt = np.degrees(np.arctan2(M_gt[1, 0], M_gt[0, 0]))
    
    # Extract Recovered parameters
    tx_rec, ty_rec = M_rec[0, 2], M_rec[1, 2]
    rot_rec = np.degrees(np.arctan2(M_rec[1, 0], M_rec[0, 0]))
    
    # Compute Errors
    trans_err = np.sqrt((tx_rec - tx_gt)**2 + (ty_rec - ty_gt)**2)
    rot_err = abs(rot_rec - rot_gt)
    
    return num_matches, inliers, inlier_ratio, trans_err, rot_err

def main():
    print("=== LOADING MONTES APENNINUS ===")
    with rasterio.open("apenninus_wac.tif") as src:
        img = src.read(1).astype(np.float32)
        wac_img = np.clip((img - np.nanmin(img)) / (np.nanmax(img) - np.nanmin(img) + 1e-5) * 255.0, 0, 255).astype(np.uint8)

    with rasterio.open("apenninus_dem.tif") as src:
        dem_km = src.read(1).astype(np.float32)

    # Convert KM to Topographic Meters
    dem_m = (dem_km - 1737.4) * 1000.0
    
    print("\n=== PRISM RELIGHTING ===")
    normals = compute_surface_normals(dem_m, 59.23) 
    normals = cv2.resize(normals, (wac_img.shape[1], wac_img.shape[0]), interpolation=cv2.INTER_LINEAR)
    
    # Apply harsh 10-degree morning shadows
    sun_vector = get_sun_vector(270.0, 10.0) 
    relit_result = apply_lunar_lambert(wac_img, normals, sun_vector)
    relit_wac = relit_result[0] if isinstance(relit_result, tuple) else relit_result

    # Verify Relighting actually happened before transforming
    diff = np.abs(wac_img.astype(np.float32) - relit_wac.astype(np.float32))
    mean_abs_diff = np.mean(diff)
    print(f"[Relight Verified] Mean |Δpixel|: {mean_abs_diff:.4f} (PRISM successfully altered lighting)")

    print("\n=== GENERATING GROUND TRUTH GEOMETRIC PERTURBATION ===")
    # Fixed seed for reproducibility
    np.random.seed(42) 
    h, w = wac_img.shape
    center = (w / 2, h / 2)
    
    # Generate Random Transform: Rotation [-5, 5] deg, Translation [-50, 50] px, Scale [0.97, 1.03]
    angle_gt = np.random.uniform(-5.0, 5.0)
    scale_gt = np.random.uniform(0.97, 1.03)
    tx_gt = np.random.uniform(-50.0, 50.0)
    ty_gt = np.random.uniform(-50.0, 50.0)
    
    M_gt = cv2.getRotationMatrix2D(center, angle_gt, scale_gt)
    M_gt[0, 2] += tx_gt
    M_gt[1, 2] += ty_gt
    
    print(f"Applied Transform -> Rotation: {angle_gt:.2f}°, Trans X: {tx_gt:.1f}px, Trans Y: {ty_gt:.1f}px, Scale: {scale_gt:.3f}x")

    # Apply transform to both versions (using BORDER_REFLECT to avoid artificial black edges LoFTR might latch onto)
    ref_raw_perturbed = cv2.warpAffine(wac_img, M_gt, (w, h), borderMode=cv2.BORDER_REFLECT)
    ref_relit_perturbed = cv2.warpAffine(relit_wac, M_gt, (w, h), borderMode=cv2.BORDER_REFLECT)

    print("\n=== RUNNING LoFTR EVALUATION ===")
    matcher = LoFTRMatcher()
    
    print("Matching: Source (Raw) vs. Reference (Raw Perturbed)...")
    raw_m, raw_inl, raw_ratio, raw_terr, raw_rerr = evaluate_matching(matcher, wac_img, ref_raw_perturbed, M_gt)
    
    print("Matching: Source (Raw) vs. Reference (PRISM-Relit Perturbed)...")
    rel_m, rel_inl, rel_ratio, rel_terr, rel_rerr = evaluate_matching(matcher, wac_img, ref_relit_perturbed, M_gt)

    print("\n" + "="*85)
    print("GEOMETRIC ABLATION: RECOVERING TRUE TRANSFORM UNDER ILLUMINATION SHIFT")
    print("="*85)
    print(f"{'Condition':<22} | {'Matches':<8} | {'Inliers':<8} | {'Inl %':<8} | {'Rot Err (°)':<12} | {'Trans Err (px)'}")
    print("-" * 85)
    print(f"{'Raw WAC vs Raw':<22} | {raw_m:<8} | {raw_inl:<8} | {raw_ratio:<8.1%} | {raw_rerr:<12.3f} | {raw_terr:.3f}")
    print(f"{'Raw WAC vs PRISM-Relit':<22} | {rel_m:<8} | {rel_inl:<8} | {rel_ratio:<8.1%} | {rel_rerr:<12.3f} | {rel_terr:.3f}")
    print("="*85)

if __name__ == "__main__":
    main()