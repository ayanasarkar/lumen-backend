import torch
import kornia.feature as KF
import numpy as np

class LoFTRMatcher:
    def __init__(self, device=None):
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = device
            
        print(f"[LoFTR] Initializing on {self.device}...")
        self.matcher = KF.LoFTR(pretrained='outdoor').to(self.device).eval()

    def _prepare_tensor(self, img_np):
        """Convert numpy image (H, W) [0, 255] to Tensor (1, 1, H, W) [0, 1]"""
        # STRICT ASSERTIONS ADDED HERE
        if not isinstance(img_np, np.ndarray):
            raise TypeError(f"[LoFTR Data Error] Expected numpy array, got {type(img_np)}. Did a geotransform tuple leak into the image variable?")
        if len(img_np.shape) != 2:
            raise ValueError(f"[LoFTR Data Error] Expected 2D grayscale image (H, W), got shape {img_np.shape}.")
            
        t = torch.tensor(img_np, dtype=torch.float32).unsqueeze(0).unsqueeze(0) / 255.0
        return t.to(self.device)

    def match(self, img0_np, img1_np):
        """
        Takes two numpy arrays (H,W), returns matching points and confidences.
        """
        img0_t = self._prepare_tensor(img0_np)
        img1_t = self._prepare_tensor(img1_np)

        with torch.no_grad():
            matches = self.matcher({"image0": img0_t, "image1": img1_t})
        
        # Extract to numpy for handoff
        mkpts0 = matches['keypoints0'].cpu().numpy()
        mkpts1 = matches['keypoints1'].cpu().numpy()
        conf = matches['confidence'].cpu().numpy()
        
        return mkpts0, mkpts1, conf