"""
Run the existing, already-working PRISM + LoFTR pipeline on the IIRS<->WAC
pair (LUMEN AI/ML track, Sections 5-6-7-8 of the task brief).

This file does NOT touch:
  - prism.py's relighting math (ratio correction, clamping, log
    compression) -- call prism.relight_reference(), don't open it.
  - run_real_validation.py's metric logic -- shell out to it as-is.
  - modality_bridge.py's averaging logic -- reuse it, don't rewrite it.

Everything below just wires the existing pieces together for the new
data pair, exactly per the call shape in Section 6 of the brief. If any
of these function names are slightly off from the real repo, that's a
"ask Wrik" fix, not a "guess and patch" fix.
"""

import subprocess
import sys
from pathlib import Path

import prism
import match_loftr
from modality_bridge import reduce_hyperspectral_cube  # reuse, don't rewrite

from prepare_iirs_wac_data import load_and_crop_site, sanity_check

SITE_NAME = "iirs_wac_equatorial_01"
OUTPUT_DIR = Path(f"../data/sites/{SITE_NAME}/outputs")

# Section 5: which band / method was used as the grayscale proxy.
# Fill this in truthfully once you've picked one — this is the one
# sentence the brief asks for, not decoration.
HYPERSPECTRAL_SIMPLIFICATION_NOTE = (
    "Used band <N> as a grayscale proxy for the full IIRS cube "
    "(alternative: PCA/average composite via modality_bridge); this is a "
    "stand-in for the real spectral bridge, which is out of MVP scope."
)


def get_sun_angles(iirs_cube, wac_crop):
    """
    Pull source/reference sun angles from product metadata / SPICE.
    Placeholder wiring — the brief notes these come from SPICE / product
    metadata (Section 6); point this at whatever Wrik's OHRC/NAC site
    uses for the same lookup so the two sites stay consistent.
    """
    iirs_sun_angle = getattr(iirs_cube, "sun_angle", None)
    wac_sun_angle = getattr(wac_crop, "sun_angle", None)
    if iirs_sun_angle is None or wac_sun_angle is None:
        raise ValueError(
            "Sun angle metadata missing from IIRS/WAC products — check "
            "the PDS4 label / SPICE kernel lookup before proceeding."
        )
    return iirs_sun_angle, wac_sun_angle


def run_pipeline():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Section 4: load + crop + sanity-check -------------------------
    iirs_cube, wac_crop, dem_crop = load_and_crop_site()
    sanity_check(iirs_cube, wac_crop, dem_crop)

    # --- Section 5: hyperspectral -> single grayscale-like image -------
    iirs_grayscale = reduce_hyperspectral_cube(iirs_cube)

    # --- Section 6: relight + match, exact call shape from the brief ---
    iirs_sun_angle, wac_sun_angle = get_sun_angles(iirs_cube, wac_crop)

    relit_reference = prism.relight_reference(
        reference_image=wac_crop,
        dem_tile=dem_crop,
        source_sun_angle=iirs_sun_angle,
        reference_sun_angle=wac_sun_angle,
    )

    matches = match_loftr.run_matching(
        source_image=iirs_grayscale,
        reference_image=relit_reference,
    )

    # --- Section 8.3: side-by-side image for eyeballing -----------------
    # Wire this to whatever plotting helper Wrik's OHRC/NAC site used,
    # so the deliverable image is in the same format as the rest of the
    # team's sites (raw reference vs relit reference vs source, same crop).

    return iirs_grayscale, wac_crop, relit_reference, matches


def run_validation():
    """
    Section 6: shell out to the existing, locked validation script.
    Don't reimplement its metric logic here.
    """
    log_path = OUTPUT_DIR / "iirs_wac_validation.log"
    with open(log_path, "w") as log_file:
        result = subprocess.run(
            [sys.executable, "run_real_validation.py"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    print(log_path.read_text())
    if result.returncode != 0:
        print(
            f"run_real_validation.py exited with code {result.returncode} "
            "— check the log above before trusting any numbers."
        )
    return log_path


if __name__ == "__main__":
    print(HYPERSPECTRAL_SIMPLIFICATION_NOTE)
    run_pipeline()
    run_validation()
