import os
import numpy as np
import cv2
import rasterio

from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

def get_safe_crop(img, x, y, size=25):
    """Safely extracts a crop padded by reflection to avoid boundary crashes."""
    x, y = int(x), int(y)
    padded = cv2.copyMakeBorder(img, size, size, size, size, cv2.BORDER_REFLECT)
    # Coordinates in padded image are shifted by 'size'
    px, py = x + size, y + size
    return padded[py-size:py+size, px-size:px+size]

def save_crops_montage(indices, img_src, img_ref, pts_src, pts_ref, errors, filename):
    """Saves a side-by-side montage of Source and Relit Reference crops."""
    rows = []
    for i in indices:
        c_src = get_safe_crop(img_src, pts_src[i][0], pts_src[i][1])
        c_ref = get_safe_crop(img_ref, pts_ref[i][0], pts_ref[i][1])
        
        # Resize for better visual inspection
        c_src = cv2.resize(c_src, (150, 150), interpolation=cv2.INTER_NEAREST)
        c_ref = cv2.resize(c_ref, (150, 150), interpolation=cv2.INTER_NEAREST)
        
        # Add text overlay showing the localization error
        cv2.putText(c_src, f"Err: {errors[i]:.2f}px", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 1, cv2.LINE_AA)
        
        row = np.hstack([c_src, c_ref])
        rows.append(row)
        
    montage = np.vstack(rows)
    cv2.imwrite(filename, montage)

def main():
    print("=== LOADING DATA ===")
    with rasterio.open("apenninus_wac.tif") as src:
        img = src.read(1).astype(np.float32)
        ref_native = np.clip((img - np.nanmin(img)) / (np.nanmax(img) - np.nanmin(img) + 1e-5) * 255.0, 0, 255).astype(np.uint8)

    with rasterio.open("apenninus_dem.tif") as src:
        dem_km = src.read(1).astype(np.float32)
    dem_m = (dem_km - 1737.4) * 1000.0
    
    normals = compute_surface_normals(dem_m, 59.23) 
    normals = cv2.resize(normals, (ref_native.shape[1], ref_native.shape[0]), interpolation=cv2.INTER_LINEAR)

    print("\n=== REPLICATING CONDITION 3 (Mismatched, Corrected) ===")
    sun_az, sun_el = 200.0, 60.0
    print(f"Target Sun Azimuth : {sun_az}°")
    print(f"Target Sun Elevation: {sun_el}°")
    
    sun_source = get_sun_vector(sun_az, sun_el)
    
    # 1. Source (Simulated)
    source_result = apply_lunar_lambert(ref_native, normals, sun_source)
    source_img = source_result[0] if isinstance(source_result, tuple) else source_result

    # 2. Relit Reference
    ref_relit_result = apply_lunar_lambert(ref_native, normals, sun_source)
    ref_relit = ref_relit_result[0] if isinstance(ref_relit_result, tuple) else ref_relit_result

    print("\n=== STEP 1: VISUAL DIFF MAP ===")
    diff_img = cv2.absdiff(ref_native, ref_relit)
    diff_norm = cv2.normalize(diff_img, None, 0, 255, cv2.NORM_MINMAX)
    
    cv2.imwrite("diag_1a_raw_wac.png", ref_native)
    cv2.imwrite("diag_1b_relit_wac.png", ref_relit)
    cv2.imwrite("diag_1c_diff_map.png", diff_norm)
    print("Saved: diag_1a_raw_wac.png, diag_1b_relit_wac.png, diag_1c_diff_map.png")

    print("\n=== STEP 3: QUANTITATIVE EDGE ALIGNMENT ===")
    # Extract shadow edges using Canny edge detector
    edges_raw = cv2.Canny(ref_native, 50, 150)
    edges_relit = cv2.Canny(ref_relit, 50, 150)
    
    # Dilate raw edges to allow for 1-pixel natural shifting tolerance
    kernel = np.ones((3,3), np.uint8)
    dilated_raw_edges = cv2.dilate(edges_raw, kernel, iterations=1)
    
    # Identify "Ghost" Edges (edges in relit that do NOT overlap native shadows)
    ghost_edges = cv2.bitwise_and(edges_relit, cv2.bitwise_not(dilated_raw_edges))
    
    total_relit_edge_pixels = np.sum(edges_relit > 0)
    misaligned_edge_pixels = np.sum(ghost_edges > 0)
    misalignment_ratio = misaligned_edge_pixels / max(total_relit_edge_pixels, 1)
    
    print(f"Total Relit Edge Pixels : {total_relit_edge_pixels}")
    print(f"Ghost/Misaligned Edges  : {misaligned_edge_pixels}")
    print(f"Shadow Misalignment     : {misalignment_ratio:.1%} of relit edges are new/ghosted.")

    print("\n=== STEP 2: MATCHER LOCALIZATION ERROR EXTRACTION ===")
    # Apply standard perturbation
    np.random.seed(42) 
    h, w = ref_native.shape
    center = (w / 2, h / 2)
    M_gt = cv2.getRotationMatrix2D(center, -1.25, 1.027)
    M_gt[0, 2] += 23.2
    M_gt[1, 2] += 9.9
    
    ref_relit_warped = cv2.warpAffine(ref_relit, M_gt, (w, h), borderMode=cv2.BORDER_REFLECT)

    matcher = LoFTRMatcher()
    m0, m1, conf = matcher.match(source_img, ref_relit_warped)
    
    # Calculate exact per-match localization error against Ground Truth
    m0_homogeneous = np.hstack([m0, np.ones((len(m0), 1))])
    expected_m1 = (M_gt @ m0_homogeneous.T).T
    errors = np.linalg.norm(m1 - expected_m1, axis=1)
    
    sorted_idx = np.argsort(errors)
    best_idx = sorted_idx[:5]
    worst_idx = sorted_idx[-5:] # Highest error
    
    save_crops_montage(best_idx, source_img, ref_relit_warped, m0, m1, errors, "diag_2_best_matches.png")
    save_crops_montage(worst_idx, source_img, ref_relit_warped, m0, m1, errors, "diag_2_worst_matches.png")
    print(f"Saved: diag_2_best_matches.png (Avg Err: {np.mean(errors[best_idx]):.2f}px)")
    print(f"Saved: diag_2_worst_matches.png (Avg Err: {np.mean(errors[worst_idx]):.2f}px)")

    print("\n" + "="*80)
    print("VERDICT ON ALBEDO-CONFOUND (DOUBLE-SHADOW) HYPOTHESIS")
    print("="*80)
    if misalignment_ratio > 0.35:
        print("VERDICT: The quantitative evidence SUPPORTS the 'compounding shadows' hypothesis.")
        print(f"With {misalignment_ratio:.1%} of shadow edges shifted into new, non-overlapping")
        print("locations, PRISM is injecting a secondary ghost shadow pattern over the native")
        print("WAC shadows. This creates dual, ambiguous local edge descriptors that severely")
        print("degrade LoFTR's sub-pixel geometric localization precision (Rotation/Translation Error),")
        print("even while aggregate region similarity keeps the raw match count high.")
    else:
        print("VERDICT: Evidence DOES NOT clearly support the double-shadow hypothesis.")
        print("Shadow misalignment is relatively low. The precision drop is likely caused by")
        print("a genuine geometric distortion introduced by the DEM relighting step itself,")
        print("unrelated to albedo compounding.")
    print("="*80)

if __name__ == "__main__":
    main()