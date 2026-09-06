# LUMEN AI/ML Architecture

## LoFTR Fallback Protocol (Pending Real Data)
If the domain gap on real lunar imagery causes LoFTR's performance to degrade, the automated pipeline will trigger a fallback to Classical SIFT + MAGSAC++. 

**Trigger Threshold:** 
If `RANSAC_Inliers < 25` OR `Average_Confidence < 0.25` on the PRISM-relit pair, the pipeline will discard the LoFTR tensor output, initialize OpenCV SIFT, and compute Lowe's Ratio Test matches.