"""
IIRS <-> WAC site prep (LUMEN AI/ML track, Section 4 of the task brief).

Owns: downloading/locating the three inputs for one site, cropping WAC+DEM
to the IIRS footprint, and the provenance sanity-check before anything
gets run through the pipeline.

Does NOT touch: prism.py's relighting math or run_real_validation.py's
metric logic. This file only prepares inputs for those.

Reuses Wrik's real_site_loader.py for the crop-to-common-footprint step
(Section 4b) instead of reimplementing it -- import it, don't rewrite it.
If the actual function name in real_site_loader.py differs from
`crop_to_common_footprint` below, that's a one-line fix once you check
the real signature with Wrik; don't guess further than this.
"""

from pathlib import Path

# --- reused from the existing (locked) pipeline -----------------------
# Ask Wrik for the exact import path if this doesn't match the repo.
from real_site_loader import crop_to_common_footprint  # noqa: E402

SITE_NAME = "iirs_wac_equatorial_01"
SITE_DIR = Path(f"../data/sites/{SITE_NAME}")

IIRS_IMG_PATH = SITE_DIR / "iirs_source.img"       # PDS4 .IMG, calibrated
IIRS_LABEL_PATH = SITE_DIR / "iirs_source.xml"     # PDS4 label
WAC_MOSAIC_PATH = SITE_DIR / "wac_global_100m.tif" # LROC WAC 100m mosaic crop
DEM_PATH = SITE_DIR / "sldem2015_tile.tif"         # same SLDEM2015 tile Wrik uses


def load_and_crop_site(
    iirs_img_path: Path = IIRS_IMG_PATH,
    wac_mosaic_path: Path = WAC_MOSAIC_PATH,
    dem_path: Path = DEM_PATH,
):
    """
    Crop the WAC mosaic and DEM tile to the IIRS footprint using the
    existing (already-working) crop helper.

    Returns (iirs_cube, wac_crop, dem_crop) — raw, uncropped-IIRS,
    cropped WAC and DEM. Hyperspectral reduction of iirs_cube happens
    separately, in modality_bridge.py (Section 5), not here.
    """
    iirs_cube, wac_crop, dem_crop = crop_to_common_footprint(
        source_path=iirs_img_path,
        reference_path=wac_mosaic_path,
        dem_path=dem_path,
    )
    return iirs_cube, wac_crop, dem_crop


def sanity_check(iirs_cube, wac_crop, dem_crop) -> None:
    """
    Section 4d: print shape / pixel scale / CRS for each product and
    confirm all three spatially overlap before running anything further.

    This is the same provenance check Wrik runs for every new site — it's
    what caught the OHRC/NAC "too similar" problem early. Don't skip it,
    and don't proceed past a failed check just to keep moving.
    """
    for name, product in [("IIRS", iirs_cube), ("WAC", wac_crop), ("DEM", dem_crop)]:
        shape = getattr(product, "shape", None)
        pixel_scale = getattr(product, "pixel_scale", None)
        crs = getattr(product, "crs", None)
        print(f"[{name}] shape={shape} pixel_scale={pixel_scale} crs={crs}")

    # Explicit overlap check — don't assume the crop succeeded silently.
    bounds = [getattr(p, "bounds", None) for p in (iirs_cube, wac_crop, dem_crop)]
    if any(b is None for b in bounds):
        print(
            "WARNING: at least one product has no `.bounds` attribute — "
            "can't confirm spatial overlap automatically. Check manually "
            "before proceeding, per Section 4d."
        )
    else:
        print(f"Bounds — IIRS: {bounds[0]}  WAC: {bounds[1]}  DEM: {bounds[2]}")
        print(
            "Confirm these three boxes actually overlap the crater/region "
            "you intend before moving to Section 5."
        )


if __name__ == "__main__":
    iirs_cube, wac_crop, dem_crop = load_and_crop_site()
    sanity_check(iirs_cube, wac_crop, dem_crop)
