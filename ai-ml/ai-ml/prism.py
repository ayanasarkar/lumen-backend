import numpy as np
import cv2

SHADOW_RELIABILITY_FLOOR = 0.03
SHADOW_RELIABILITY_CEILING = 0.08
DEFAULT_SOFTENING_FACTOR = 0.50

def compute_surface_normals(dem, pixel_scale, nodata_val=-9999.0):
    """Computes per-pixel surface normals from a DEM, safely masking nodata."""
    dem_safe = np.array(dem, dtype=np.float32, copy=True)
    
    nodata_mask = np.isclose(dem_safe, nodata_val, atol=1e-3) | np.isnan(dem_safe)
    dem_safe[nodata_mask] = np.nan
    
    dy, dx = np.gradient(dem_safe, pixel_scale, pixel_scale)
    
    norm = np.sqrt(dx**2 + dy**2 + 1.0)
    nx = -dx / norm
    ny = -dy / norm
    nz = 1.0 / norm
    
    nx[nodata_mask] = np.nan
    ny[nodata_mask] = np.nan
    nz[nodata_mask] = np.nan
    
    return np.stack([nx, ny, nz], axis=-1)

def get_sun_vector(azimuth_deg, elevation_deg):
    """Converts azimuth and elevation to a normalized Cartesian Sun vector."""
    az_rad = np.radians(azimuth_deg)
    el_rad = np.radians(elevation_deg)
    
    sx = np.cos(el_rad) * np.sin(az_rad)
    sy = np.cos(el_rad) * np.cos(az_rad)
    sz = np.sin(el_rad)
    
    vec = np.array([sx, sy, sz], dtype=np.float32)
    return vec / np.linalg.norm(vec)

def compute_lunar_lambert_shading(normals, sun_vector):
    """Computes pure McEwen Lunar-Lambert shading field for a given Sun vector."""
    cos_i = np.sum(normals * sun_vector, axis=-1)
    cos_i = np.clip(cos_i, 0.0, 1.0)
    cos_e = np.clip(normals[..., 2], 1e-4, 1.0)
    
    shading = 2.0 * cos_i / (cos_i + cos_e)
    return np.nan_to_num(shading, nan=0.0)

def apply_lunar_lambert(
    raw_ref_img,
    normals,
    src_sun_vector,
    ref_sun_vector=None,
    softening_factor=DEFAULT_SOFTENING_FACTOR,
    shadow_floor=SHADOW_RELIABILITY_FLOOR,
    shadow_ceil=SHADOW_RELIABILITY_CEILING
):
    """
    Physically relights reference image using log-space tone-compressed
    photometric ratios and feathered shadow boundary blending.
    """
    raw_ref = np.array(raw_ref_img, dtype=np.float32)
    target_h, target_w = raw_ref.shape[:2]
    
    # 1. Upsample surface normals to match reference image resolution
    if normals.shape[:2] != (target_h, target_w):
        normals = cv2.resize(normals, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        norm = np.linalg.norm(normals, axis=-1, keepdims=True)
        norm[norm == 0] = 1.0
        normals = normals / norm

    # 2. Target and Original Illumination fields
    s_target = compute_lunar_lambert_shading(normals, src_sun_vector)
    if ref_sun_vector is not None:
        s_original = compute_lunar_lambert_shading(normals, ref_sun_vector)
    else:
        default_ref_sun = get_sun_vector(135.0, 50.0)
        s_original = compute_lunar_lambert_shading(normals, default_ref_sun)

    # 3. Raw Photometric Ratio Computation
    safe_s_original = np.maximum(s_original, shadow_floor)
    safe_s_target = np.maximum(s_target, 1e-4)
    raw_correction = safe_s_target / safe_s_original

    # 4. Soft Log-Space Tone Compression
    log_corr = np.log(raw_correction)
    compressed_log = np.tanh(log_corr / softening_factor) * softening_factor
    smooth_correction = np.exp(compressed_log)

    # 5. Smooth Feathered Alpha Matte across Shadow Boundaries
    alpha_raw = np.clip((s_original - shadow_floor) / (shadow_ceil - shadow_floor), 0.0, 1.0)
    alpha_smooth = cv2.GaussianBlur(alpha_raw, (15, 15), 3.0)

    # 6. Apply Correction and Blend
    relit_corrected = raw_ref * smooth_correction
    relit_unclipped = alpha_smooth * relit_corrected + (1.0 - alpha_smooth) * raw_ref

    unclipped_min = float(np.min(relit_unclipped))
    unclipped_max = float(np.max(relit_unclipped))

    # 7. Final Safe Integer Cast
    relit_final = np.clip(relit_unclipped, 0.0, 255.0).astype(np.uint8)
    
    blend_metadata = {
        "softening_factor": softening_factor,
        "raw_ratio_range": (float(np.min(raw_correction)), float(np.max(raw_correction))),
        "compressed_ratio_range": (float(np.min(smooth_correction)), float(np.max(smooth_correction))),
        "unclipped_min": unclipped_min,
        "unclipped_max": unclipped_max,
        "unreliable_fraction": float(np.mean(alpha_smooth < 0.5) * 100.0)
    }

    return relit_final, smooth_correction, blend_metadata