# FINDINGS: Albedo-Confound and Double-Shadow Degradation in PRISM-lite

**Date:** September 2026  
**Track:** AI/ML (LUMEN Project)  
**Subject:** Diagnostic Validation of PRISM-lite on High-Relief Lunar Terrain (Montes Apenninus)

## 1. The Hypothesis
During real-terrain validation, we hypothesized that the MVP-scope decision to use a raw, uncorrected image as an "albedo proxy" would actively degrade deep-learning matching on high-relief terrain. Specifically: because the native image already contains baked-in shadows, applying PRISM relighting over it would create a "double-shadow" or ghosting effect. We hypothesized this would confuse LoFTR's precise sub-pixel edge localization, resulting in lower precision (higher transform error) compared to an uncorrected mismatched image.

## 2. 3-Condition Relighting Ablation
To test this, we simulated a "Hard Case" illumination mismatch (Az 200°, El 60°) against the native terrain, applied a known Ground Truth geometric perturbation, and evaluated whether PRISM relighting could recover the lost accuracy.

| Condition | Matches | Inliers | Inl % | Rot Err (°) | Trans Err (px) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Same-Illum Ceiling** | 3124 | 1300 | 41.6% | 0.178 | 2.440 |
| **2. Mismatched (Uncorr)** | 3086 | 1069 | 34.6% | 0.277 | 1.892 |
| **3. Mismatched (Correct)** | 3128 | 1071 | 34.2% | **0.451** | 1.916 |

## 3. The Verdict
**Relighting via an albedo proxy did not improve matching accuracy.** 
Condition 3 (Relit/Corrected) failed to beat Condition 2 (Uncorrected) in inlier percentage. Crucially, the geometric localization degraded severely: Rotation Error nearly doubled from `0.277°` to `0.451°`, despite the raw inlier count remaining effectively identical (1069 vs 1071).

## 4. Diagnostic Evidence
A secondary diagnostic script was run to extract the physical shadow alignment and the worst-performing local patches:

*   **Quantitative Edge Misalignment:** Canny edge detection revealed that **39.6% of PRISM-relit shadow edges were misaligned/ghosted** relative to the native WAC shadows.
*   **Visual Evidence (Saved to disk):**
    *   `diag_1c_diff_map.png` — *Caption: Absolute pixel difference map highlighting the non-overlapping, dual-shadow boundaries injected by the relighting step near crater rims.*
    *   `diag_2_best_matches.png` — *Caption: Montage of 5 matches with the lowest localization error (~0.10px); patches generally landed on clean geometry without conflicting shadow overlaps.*
    *   `diag_2_worst_matches.png` — *Caption: Montage of 5 matches with the highest localization error (~7.49px); patches demonstrate LoFTR being spatially pulled off-target by ambiguous, doubled shadow edges.*

## 5. Root Cause
The degradation is caused directly by the **raw-image-as-albedo-proxy** shortcut. The raw WAC image possesses native shadows dictated by the Sun angle at its time of capture. PRISM calculates a *new* shadow map based on the target Sun angle and multiplies it against the proxy. Rather than moving the shadow, this layers a second shadow over the terrain. Advanced CNNs like LoFTR rely heavily on sharp local contrast edges for sub-pixel localization; presenting the network with dual, slightly-offset shadow edges forces ambiguous keypoint registration, spiking the rotation/translation error.

## 6. The Named Upgrade Path
This structural limitation was identified as a known risk prior to testing. The formal upgrade path is implementing true **Shape-from-Shading (SfS)**. SfS mathematically strips the native shading from the reference image to recover the true, flat photometric albedo *before* PRISM casts the new shadows. This ensures only one shadow edge exists in the final render. Because SfS requires complex, iterative photometric inversion, it was explicitly scoped out of the 36-hour hackathon MVP and is slated as future work.

---

## 7. What this does and doesn't affect

*   **What it DOES NOT affect (The Pipeline):** The pipeline architecture is fundamentally sound. It runs end-to-end securely, handles automated `rasterio` georeferencing, avoids GDAL streaming instability entirely by caching the DEM tile locally rather than reading windowed crops over HTTP, executes the AI matchers, and successfully writes the required JSON contract and GeoTIFFs to the filesystem. It will not block the live demo or Backend B integration.
*   **What it DOES affect (The Claimed Accuracy):** We cannot claim that the current PRISM-lite MVP improves sub-pixel accuracy on high-relief lunar terrain. The current proxy implementation measurably reduces geometric precision. 
*   **Hackathon Status:** We will present this finding honestly to the judges. It proves we rigorously stress-tested our own algorithm, quantitatively identified its architectural limits, and possess the domain knowledge to define the exact mathematical upgrade (SfS) required for the production version.

