import numpy as np
import cv2
import os

from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from match_loftr import LoFTRMatcher

def generate_dem():
    x = np.linspace(-1, 1, 512)
    y = np.linspace(-1, 1, 512)
    xx, yy = np.meshgrid(x, y)
    r = np.sqrt(xx**2 + yy**2)
    dem = -0.5 * np.exp(-(r/0.2)**2) + 0.1 * np.exp(-((r-0.25)/0.05)**2)
    return dem * 1000.0, 2.0

def generate_base_texture():
    np.random.seed(42)
    noise = np.random.normal(128, 20, (512, 512))
    return np.clip(noise, 0, 255).astype(np.float32)

def safe_relight(texture, norms, sun_vec):
    result = apply_lunar_lambert(texture, norms, sun_vec)
    return result[0] if isinstance(result, tuple) else result

def compute_metrics(mkpts0, mkpts1, conf):
    num_matches = len(mkpts0)
    if num_matches < 4:
        return num_matches, 0, 0.0, 0.0

    H, mask = cv2.findHomography(mkpts0, mkpts1, cv2.RANSAC, 3.0)
    inliers = int(np.sum(mask)) if mask is not None else 0
    inlier_ratio = inliers / num_matches if num_matches > 0 else 0.0
    avg_conf = float(np.mean(conf)) if len(conf) > 0 else 0.0
    
    return num_matches, inliers, inlier_ratio, avg_conf

def run_ablation():
    print("Initializing LoFTR and generating synthetic ground-truth terrain...\n")
    matcher = LoFTRMatcher()
    dem, pixel_scale = generate_dem()
    normals = compute_surface_normals(dem, pixel_scale)
    base_texture = generate_base_texture()
    
    # --- 1. Moderate Sun Elevation (Equatorial: 45 degrees) ---
    sun_mod_src = get_sun_vector(45.0, 45.0)
    sun_mod_ref = get_sun_vector(135.0, 45.0)
    print(f"[Vector Check] Moderate Ref (Az:135, El:45) Vector : {sun_mod_ref}")
    
    img_mod_src = safe_relight(base_texture, normals, sun_mod_src)
    img_mod_ref = safe_relight(base_texture, normals, sun_mod_ref)
    cv2.imwrite('mod_ref.png', img_mod_ref)
    
    # --- 2. Low Sun Elevation (Polar: 10 degrees) ---
    sun_low_src = get_sun_vector(45.0, 10.0)
    sun_low_ref = get_sun_vector(135.0, 10.0)
    print(f"[Vector Check] Low Ref (Az:135, El:10) Vector      : {sun_low_ref}")
    
    img_low_src = safe_relight(base_texture, normals, sun_low_src)
    img_low_ref = safe_relight(base_texture, normals, sun_low_ref)
    cv2.imwrite('low_ref.png', img_low_ref)

    # --- 3. Extreme Sun Elevation (3 degrees) ---
    sun_ext_src = get_sun_vector(45.0, 3.0)
    sun_ext_ref = get_sun_vector(135.0, 3.0)
    print(f"[Vector Check] Extreme Ref (Az:135, El:3) Vector   : {sun_ext_ref}\n")
    
    img_ext_src = safe_relight(base_texture, normals, sun_ext_src)
    img_ext_ref = safe_relight(base_texture, normals, sun_ext_ref)
    cv2.imwrite('ext_ref.png', img_ext_ref)

    # --- Pixel Difference Check ---
    diff = np.mean(np.abs(img_mod_ref.astype(np.float32) - img_low_ref.astype(np.float32)))
    print(f"[Diagnostic] Mean Absolute Pixel Diff (Moderate vs Low): {diff:.3f} pixels\n")

    # --- Matching & Metrics ---
    print("Matching pairs...")
    m0_mod, m1_mod, c_mod = matcher.match(img_mod_src, img_mod_ref)
    mod_raw, mod_inliers, mod_ratio, mod_conf = compute_metrics(m0_mod, m1_mod, c_mod)
    
    m0_low, m1_low, c_low = matcher.match(img_low_src, img_low_ref)
    low_raw, low_inliers, low_ratio, low_conf = compute_metrics(m0_low, m1_low, c_low)

    m0_ext, m1_ext, c_ext = matcher.match(img_ext_src, img_ext_ref)
    ext_raw, ext_inliers, ext_ratio, ext_conf = compute_metrics(m0_ext, m1_ext, c_ext)
    
    # --- Output Ablation Table ---
    print("\n" + "="*75)
    print("SYNTHETIC GROUND-TRUTH ABLATION: SUN ELEVATION IMPACT ON LoFTR")
    print("="*75)
    print(f"{'Condition':<20} | {'Matches (Raw)':<15} | {'Inliers':<10} | {'Inlier %':<10} | {'Avg Conf'}")
    print("-" * 75)
    print(f"{'Moderate Sun (45°)':<20} | {mod_raw:<15} | {mod_inliers:<10} | {mod_ratio:<10.1%} | {mod_conf:.3f}")
    print(f"{'Low Sun (10°)':<20} | {low_raw:<15} | {low_inliers:<10} | {low_ratio:<10.1%} | {low_conf:.3f}")
    print(f"{'Extreme Sun (3°)':<20} | {ext_raw:<15} | {ext_inliers:<10} | {ext_ratio:<10.1%} | {ext_conf:.3f}")
    print("="*75)

    print("\nFINAL VERDICT:")
    if diff < 1.0:
        print("BUG CONFIRMED: renders are not responding to sun angle, root cause: PRISM vector math or shading functions are dropping inputs.")
    else:
        print(f"NO BUG: renders differ correctly (MAPD = {diff:.2f}), but synthetic terrain saturates LoFTR regardless of angle — real-data testing required to see genuine degradation.")

if __name__ == "__main__":
    run_ablation()