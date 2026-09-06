import os
import numpy as np
import rasterio
from rasterio.transform import from_origin

# Setup a local scratch cache for mock rasters
MOCK_DIR = os.path.join(os.path.dirname(__file__), "mock_data_cache")
os.makedirs(MOCK_DIR, exist_ok=True)


def _write_mock_geotiff(filename, data, pixel_scale=2.0, is_raw=False):
    filepath = os.path.join(MOCK_DIR, filename)

    # Simulate coordinate space: identity transform for raw, calibrated transform otherwise
    if is_raw:
        transform = rasterio.transform.Affine.identity()
        crs = None
    else:
        transform = from_origin(0.0, 0.0, pixel_scale, pixel_scale)
        # Moon Equidistant Cylindrical / Sphere radius 1737.4 km
        crs = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"

    if data.ndim == 2:
        count = 1
        height, width = data.shape
        dtype = data.dtype
    else:
        count, height, width = data.shape
        dtype = data.dtype

    with rasterio.open(
        filepath, 'w',
        driver='GTiff',
        height=height,
        width=width,
        count=count,
        dtype=dtype,
        crs=crs,
        transform=transform,
        compress='lzw'
    ) as dst:
        if count == 1:
            dst.write(data, 1)
        else:
            dst.write(data)

    return filepath


def get_dem(site_id):
    """Returns synthetic DEM data and guarantees mock file exists on disk."""
    if "real" in site_id:
        dem_path = os.path.join(MOCK_DIR, f"{site_id}_dem.tif")
        if not os.path.exists(dem_path):
            dem = np.ones((512, 512), dtype=np.float32) * 500.0
            _write_mock_geotiff(f"{site_id}_dem.tif", dem, pixel_scale=59.0)
        return dem_path, 59.0

    x, y = np.linspace(-1, 1, 512), np.linspace(-1, 1, 512)
    xx, yy = np.meshgrid(x, y)
    r = np.sqrt(xx**2 + yy**2)
    dem = (-0.5 * np.exp(-(r / 0.2)**2) + 0.1 * np.exp(-((r - 0.25) / 0.05)**2)) * 1000.0
    dem = dem.astype(np.float32)

    dem_path = _write_mock_geotiff(f"{site_id}_dem.tif", dem, pixel_scale=2.0)
    return dem_path, 2.0


def get_products_for_site(site_id):
    """Testing the real rasterio file-loading branch with actual GeoTIFFs."""
    return {
        "source_image": "real_geotiff.tif",
        "reference_image": "real_geotiff.tif",
        "type": "ohrc_nac"
    }


def get_spice_kernels(site_id):
    if "polar" in site_id:
        return {
            "source_sun_azimuth": 90.0,
            "source_sun_elevation": 2.0,
            "ref_sun_azimuth": 270.0,
            "ref_sun_elevation": 5.0,
            "sun_azimuth": 90.0,
            "sun_elevation": 2.0
        }
    else:
        # Source (OHRC): Morning Sun (Az 45°, El 25°)
        # Reference (NAC): Opposing Afternoon Sun (Az 225°, El 55°)
        return {
            "source_sun_azimuth": 45.0,
            "source_sun_elevation": 25.0,
            "ref_sun_azimuth": 225.0,
            "ref_sun_elevation": 55.0,
            "sun_azimuth": 45.0,
            "sun_elevation": 25.0
        }


def register_run_in_db(run_id, site_id, matches_json_path, relit_image_path):
    print(f"[MOCK DB INSERT] Registered Run: {run_id} for Site: {site_id}")
    return True