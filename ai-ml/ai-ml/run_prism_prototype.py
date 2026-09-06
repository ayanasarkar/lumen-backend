import matplotlib.pyplot as plt
from backend_client_stub import get_dem, get_products_for_site, get_spice_kernels
from prism import compute_surface_normals, get_sun_vector, apply_lunar_lambert

def main():
    # 1. Fetch Mock Data
    site_id = "test_site_01"
    dem, pixel_scale = get_dem(site_id)
    ref_image = get_products_for_site(site_id)["reference_image"]
    spice_data = get_spice_kernels(site_id)
    
    # 2. Run PRISM
    normals = compute_surface_normals(dem, pixel_scale)
    sun_vector = get_sun_vector(spice_data["sun_azimuth"], spice_data["sun_elevation"])
    relit_image = apply_lunar_lambert(ref_image, normals, sun_vector)
    
    # 3. Visual Validation (Sanity Check)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    axes[0].imshow(dem, cmap='terrain')
    axes[0].set_title("Mock DEM (Crater)")
    
    axes[1].imshow(ref_image, cmap='gray', vmin=0, vmax=255)
    axes[1].set_title("Raw Reference (Albedo Proxy)")
    
    axes[2].imshow(relit_image, cmap='gray', vmin=0, vmax=255)
    axes[2].set_title(f"PRISM Relit\n(Az: {spice_data['sun_azimuth']}°, El: {spice_data['sun_elevation']}°)")
    
    for ax in axes:
        ax.axis('off')
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()