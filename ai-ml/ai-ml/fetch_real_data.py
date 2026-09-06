import os
import requests
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.env import Env

WAC_URL = "https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LROC-WAC_Mosaic_global_100m_June2013.tif"

TILE_IMG_URL = "https://imbrium.mit.edu/DATA/SLDEM2015/TILES/FLOAT_IMG/SLDEM2015_512_00N_30N_000_045_FLOAT.IMG"
TILE_LBL_URL = "https://imbrium.mit.edu/DATA/SLDEM2015/TILES/FLOAT_IMG/SLDEM2015_512_00N_30N_000_045_FLOAT.LBL"
EXPECTED_IMG_SIZE = 1415577600

# Default Target: Sinus Medii
TARGET_LON = 2.0
TARGET_LAT = 1.3
TARGET_FOOTPRINT_M = 50000.0
MOON_RADIUS_M = 1737400.0


def get_cache_key(prefix, lat, lon, window_size):
    """Generates standardized filename key for spatial crops."""
    return f"{prefix}_lat{lat:.4f}_lon{lon:.4f}_w{window_size}.tif"


def download_file(url, dest_path, expected_size=None, chunk_size=8192):
    if os.path.exists(dest_path):
        if expected_size and os.path.getsize(dest_path) != expected_size:
            print(f"[!] {dest_path} size mismatch. Deleting and redownloading...")
            os.remove(dest_path)
        else:
            print(f"{dest_path} already exists and size matches, skipping download.")
            return

    print(f"Downloading {url.split('/')[-1]}...")
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"\r  {downloaded/1e6:.1f} / {total/1e6:.1f} MB", end="")
    print("\nDownload complete.")


def fetch_and_crop_wac(lat, lon, window_size_m=50000.0):
    """
    Fetches and crops WAC mosaic based on target coordinates and footprint window.
    Implements cache verification prior to remote I/O.
    """
    cache_path = get_cache_key("wac", lat, lon, int(window_size_m))
    if os.path.exists(cache_path):
        print(f"[Cache Hit] Found {cache_path}. Verifying bounds...")
        with rasterio.open(cache_path) as src:
            print(f"[Cache Verify] Embedded bounds: {src.bounds}")
        return cache_path

    print(f"\nConnecting to USGS Astrogeology WAC for footprint: lat={lat}, lon={lon}, w={window_size_m}m...")
    env_kwargs = {'GDAL_HTTP_MAX_RETRY': 5, 'GDAL_HTTP_RETRY_DELAY': 3, 'GDAL_HTTP_TIMEOUT': 120}
    with Env(**env_kwargs):
        with rasterio.open(WAC_URL) as src:
            # WAC CRS is in meters. Convert degrees to lunar equidistant cylindrical meters.
            tgt_x_m = lon * (np.pi / 180.0) * MOON_RADIUS_M
            tgt_y_m = lat * (np.pi / 180.0) * MOON_RADIUS_M

            row_off, col_off = src.index(tgt_x_m, tgt_y_m)
            pixel_scale_m = abs(src.transform.a)
            size_px = int(window_size_m / pixel_scale_m)

            window = Window(col_off - size_px // 2, row_off - size_px // 2, size_px, size_px)
            print(f"WAC Streaming pixel window {window}...")
            data = src.read(1, window=window)

            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": window.height,
                "width": window.width,
                "transform": src.window_transform(window),
                "compress": "lzw"
            })
            print(f"Saving to cache: {cache_path}")
            with rasterio.open(cache_path, "w", **out_meta) as dest:
                dest.write(data, 1)

    return cache_path


def crop_local_dem(local_lbl_path, lat, lon, window_size_m=50000.0):
    """
    Extracts calibrated topographic elevation crop from local SLDEM2015 PDS3 tile.
    Implements cache verification prior to file extraction.
    """
    cache_path = get_cache_key("dem", lat, lon, int(window_size_m))
    if os.path.exists(cache_path):
        print(f"[Cache Hit] Found {cache_path}. Verifying bounds...")
        with rasterio.open(cache_path) as src:
            print(f"[Cache Verify] Embedded bounds: {src.bounds}")
        return cache_path

    print(f"\nCropping DEM from local PDS3 file {local_lbl_path} for lat={lat}, lon={lon}, w={window_size_m}m...")
    with rasterio.open(local_lbl_path) as src:
        # Tile is 512 ppd. Top-Left is 0E, 30N.
        col_off = int((lon - 0.0) * 512.0)
        row_off = int((30.0 - lat) * 512.0)

        pixel_scale_deg = 1.0 / 512.0
        pixel_scale_m = pixel_scale_deg * (2 * np.pi * MOON_RADIUS_M) / 360.0

        size_px = int(window_size_m / pixel_scale_m)
        window = Window(col_off - size_px // 2, row_off - size_px // 2, size_px, size_px)

        print(f"DEM Reading pixel window {window} (Scale: {pixel_scale_m:.2f} m/px)...")
        data = src.read(1, window=window).astype("float32")

        scale = src.scales[0] if src.scales and src.scales[0] else 1.0
        offset = src.offsets[0] if src.offsets and src.offsets[0] else 0.0
        elevation_m = data * scale + offset

        if src.nodata is not None:
            elevation_m[data == src.nodata] = np.nan

        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": window.height,
            "width": window.width,
            "transform": src.window_transform(window),
            "compress": "lzw",
            "dtype": "float32",
            "nodata": np.nan
        })
        print(f"Saving to cache: {cache_path}")
        with rasterio.open(cache_path, "w", **out_meta) as dest:
            dest.write(elevation_m, 1)

    return cache_path


if __name__ == "__main__":
    os.makedirs("local_data", exist_ok=True)
    img_path = os.path.join("local_data", "SLDEM2015_512_00N_30N_000_045_FLOAT.IMG")
    lbl_path = os.path.join("local_data", "SLDEM2015_512_00N_30N_000_045_FLOAT.LBL")

    download_file(TILE_IMG_URL, img_path, expected_size=EXPECTED_IMG_SIZE)
    download_file(TILE_LBL_URL, lbl_path)

    wac_file = fetch_and_crop_wac(TARGET_LAT, TARGET_LON, TARGET_FOOTPRINT_M)
    dem_file = crop_local_dem(lbl_path, TARGET_LAT, TARGET_LON, TARGET_FOOTPRINT_M)

    print(f"\nTarget outputs ready:\n -> WAC: {wac_file}\n -> DEM: {dem_file}")