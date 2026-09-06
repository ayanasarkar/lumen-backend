import numpy as np

def bridge_iirs_to_grayscale(hyperspectral_cube):
    """
    MVP simplification for Part 5: 
    Averages the 256-band IIRS cube into a single grayscale proxy for LoFTR.
    In the vision roadmap, this becomes a learned spectral bridge.
    """
    print("[Modality Bridge] Averaging 256-band hyperspectral cube to grayscale...")
    # Average across the channel dimension (axis 0)
    grayscale = np.mean(hyperspectral_cube, axis=0)
    return grayscale.astype(np.uint8)