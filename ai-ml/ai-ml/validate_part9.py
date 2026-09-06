# INTERNAL VALIDATION SUITE — PART 9 (AI/ML Track Private Benchmarks)
# NOT FOR EXTERNAL USE OR OFFICIAL DEMO SLIDES (MatchMetrics owns official metrics)

import os
import cv2
import numpy as np
import torch
import rasterio

from match_loftr import LoFTRMatcher
from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert
from modality_bridge import bridge_iirs_to_grayscale
from backend_client_stub import get_products_for_site, get_dem, get_spice_kernels

# Enforce deterministic execution across all runs
torch.manual_seed(42)
np.random.seed(42)

def evaluate_pair(source_img, ref_img, matcher):
    """Runs LoFTR and computes internal sanity metrics (match count, mean conf, RANSAC inliers)."""
    mkpts0, mkpts1, conf = matcher.match(source_img, ref_img)
    match_count = len(mkpts0)
    
    if match_count < 4:
        return {
            "matches": match_count,
            "mean_conf": float(np.mean(conf)) if match_count > 0 else 0.0,
            "inlier_ratio": 0.0,
            "inlier_count": 0,
            "mkpts0": mkpts0,
            "mkpts1": mkpts1
        }
    
    # Internal consistency check via homography RANSAC
    _, mask = cv2.findHomography(mkpts0, mkpts1, cv2.RANSAC, 3.0)
    inliers = int(np.sum(mask)) if mask is not None else 0
    inlier_ratio = float(inliers / match_count) if match_count > 0 else 0.0
    
    return {
        "matches": match_count,
        "mean_conf": float(np.mean(conf)),
        "inlier_ratio": inlier_ratio,
        "inlier_count": inliers,
        "mkpts0": mkpts0,
        "mkpts1": mkpts1
    }

def compute_ground_truth_rmse(mkpts0, mkpts1, gt_checkpoints):
    """
    Computes private rough RMSE against 10-20 manually checked correspondences.
    gt_checkpoints: list of ((src_x, src_y), (ref_x, ref_y))
    """
    if len(mkpts0) < 4 or len(gt_checkpoints) == 0:
        return np.nan
    
    # Estimate transform from matches
    H, _ = cv2.findHomography(mkpts0, mkpts1, cv2.RANSAC, 3.0)
    if H is None:
        return np.nan
    
    errors = []
    for (src_pt, ref_pt) in gt_checkpoints:
        src_homo = np.array([src_pt[0], src_pt[1], 1.0])
        pred_ref = H @ src_homo
        if pred_ref[2] == 0:
            continue
        pred_ref = pred_ref[:2] / pred_ref[2]
        err = np.linalg.norm(pred_ref - np.array(ref_pt))
        errors.append(err ** 2)
        
    return np.sqrt(np.mean(errors)) if len(errors) > 0 else np.nan