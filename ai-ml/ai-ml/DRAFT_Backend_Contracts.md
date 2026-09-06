import numpy as np

def bridge_iirs_to_grayscale(hyperspectral_cube):
    """
    MVP simplification for Part 5: 
    Averages a high-SNR subset of the 256-band IIRS cube into a single grayscale proxy.
    Assumes input shape is (Channels, Height, Width).
    """
    print("[Modality Bridge] Averaging high-SNR bands of hyperspectral cube...")
    
    # Check shape to prevent axis-0 flattening disasters
    if hyperspectral_cube.shape[2] == 256:
        raise ValueError("Cube loaded as (H, W, C). Reshape to (C, H, W) before passing here.")

    # Drop the noisy extremes and water absorption bands. 
    # (Approximation: keeping a block of solid VNIR bands, e.g., bands 20 to 120)
    clean_bands = hyperspectral_cube[20:120, :, :]
    
    # Average across the channel dimension
    grayscale = np.mean(clean_bands, axis=0)
    
    # Safely normalize to 8-bit to avoid overflow on 16-bit/float inputs
    gray_min = np.nanmin(grayscale)
    gray_max = np.nanmax(grayscale)
    
    if gray_max - gray_min == 0:
        return np.zeros_like(grayscale, dtype=np.uint8)
        
    grayscale_norm = (grayscale - gray_min) / (gray_max - gray_min) * 255.0
    
    return grayscale_norm.astype(np.uint8)