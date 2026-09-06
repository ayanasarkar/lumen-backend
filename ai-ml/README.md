# LUMEN — AI/ML Track Progress README
**Lunar Unified Multi-sensor rEgistratioN Engine — Smart India Hackathon, ISRO/DoS**
**Track owner:** Wrik (AI/ML) · **Last updated:** as of this debugging session

---

## 1. What LUMEN's AI/ML track actually delivers

One JSON file per pipeline run containing pixel-space matched points between a
source image and a **PRISM-relit** reference image, each with a confidence
score — plus the relit reference image itself. Everything after that
(orthorectification, spatial thinning, sub-pixel refinement, RMSE/CUI
metrics) belongs to Backend B, not this track.

**The headline claim being tested:** relighting the reference image to match
the source's sun angle, before matching, measurably improves LoFTR match
quality vs. matching raw. This is the two-second visual the whole pitch
leans on — so it is the single most important thing to get right and prove
honestly before anything else.

---

## 2. Status at a glance

| Part | What it is | Status |
|---|---|---|
| 1 | Environment setup (VSCode + Colab) | ✅ Done |
| 2 | Lock contracts with Backend A/B | ⚠️ Not confirmed in this track's own work yet — needs explicit sign-off |
| 3 | PRISM-lite relighting | ✅ Built, math debugged and numerically sound. ⏳ Real-data proof of the core claim in progress |
| 4 | Baseline LoFTR matching script | ✅ Working, raw-vs-relit comparison functional |
| 5 | IIRS↔WAC + polar site | ❌ Not started (equatorial half is unblocked and doable now) |
| 6 | Real inference wiring to Backend A | ❌ Not started — **hard blocked** on Backend A's client library |
| 7 | Handoff (JSON + relit image + DB row) | ❌ Not started |
| 8 | Synthetic data factory / fine-tuning (stretch) | ❌ Correctly not started — premature until Part 3's claim is proven |
| 9 | Own validation, ablation, edge-case hardening | ⏳ In progress, out of planned order (started early because it had to be) |
| 10 | Integration rehearsal | ❌ Not started, depends on 6–7 |

**Rough completion: ~30–35% of the track's total scope.** Most of the time
so far has gone into Part 3, for good reason — see below.

---

## 3. The PRISM relighting debugging saga (why Part 3 took this long)

The system health check and full pipeline integration passed from day one —
every module ran, produced output, and didn't crash. But the **first real
validation run** exposed a critical problem: the relit reference was
performing *worse* than the raw reference on both match count and RMSE,
directly contradicting the project's core hypothesis.

Rather than accept that number or blindly tune parameters to hide it, we
traced it through the actual chain of causes:

1. **False alarm #1 — metric mismatch, not a real regression.**
   The raw pair's RMSE was homography-corrected (RANSAC converged); the
   relit pair's wasn't (RANSAC failed to converge) and silently fell back to
   raw nearest-correspondence distance. The two numbers were never
   comparable. **Fixed:** validation script now reports RANSAC failures
   explicitly instead of conflating two different metrics in one column.

2. **Real bug #1 — no reference self-illumination correction.**
   The shading step was applying `relit = raw_pixel * new_sun_multiplier`
   directly, without first dividing out the reference image's *own* baked-in
   illumination. Correct physical relighting requires a ratio:
   `relit = raw_pixel * (new_multiplier / reference_own_multiplier)`.
   **Fixed:** implemented the ratio correction using the reference's own
   sun geometry.

3. **Real bug #2 — divide-by-near-zero blowup.**
   Reference pixels in near-total self-shadow (multiplier ≈ 0) sent the
   correction ratio as high as 33x, blowing pixel values up to ~4779 against
   a raw range of [105,150], then hard-clipping to 0/255 and injecting fake
   contrast (std ratio 5.95x vs. a target of ~1–1.5x).
   **Fixed:** clamped the correction ratio to physically defensible bounds,
   with an explicit "unreliable shadow" mask for pixels too deep in their
   own shadow to correct reliably (passed through raw instead of forced).

4. **Real bug #3 — clamp bounds not derived from actual data range.**
   The first clamp fix used fixed bounds ([0.2, 5.0]) that still saturated
   against the real ~[105,150] pixel range. **Fixed:** clamp bounds are now
   derived dynamically from the reference image's own actual min/max.

5. **Investigated and ruled out — hard-edge artifact at the shadow-mask
   boundary.** Feathered the mask boundary as a precaution; gradient
   analysis confirmed the correction map was already smooth (mean gradient
   0.04 vs. DEM gradient 4.77) — this was not the remaining issue.

6. **Structural finding — multiplicative correction inherently inflates
   variance on a narrow-range input.** A ~22x correction swing applied to a
   45-gray-level image will always produce excess variance regardless of
   clamping. Proposed fix: log-space compression (tone-mapping style) so
   large corrections are softly compressed rather than hard-clipped.

7. **Synthetic test harness retired.** After 7 rounds, the synthetic
   512×512 toy tile had done its job (proving numerical stability) and
   stopped being a meaningful test of the real claim. Pivoted to real
   OHRC/NAC/SLDEM2015 data.

8. **First real-data attempt — DEM too coarse to matter.**
   A 256m real footprint only contained 4×4 SLDEM2015 elevation posts —
   not enough terrain detail for PRISM to act on. Raw and relit results
   were near-identical to 3 significant figures, which is itself informative
   (relighting can't do anything if the DEM can't resolve the terrain) but
   not yet a real test.

9. **Second real-data attempt — implausibly perfect result, flagged as
   suspicious rather than accepted.**
   A 3km footprint (51×51 DEM posts) produced 99%+ inlier rates and
   ~0.05px RMSE — roughly 10x better than the published ISRO/SAC baseline's
   *best* method (SuperGlue, 0.51–1.9px). Combined with OHRC and NAC
   reporting identical native pixel scale (both instruments should differ),
   this was correctly identified as likely synthetic source/reference data
   sharing an underlying render, not genuine independent imagery — **not**
   accepted as a real positive result.

**Current state:** the relighting math itself (ratio correction, clamping,
log-space compression) is believed sound. What has **not yet been proven**
is whether it helps on real, independently-acquired, verifiably-real OHRC +
NAC + SLDEM2015 data. That validation is in progress now — manually sourced
from ISSDC/PRADAN (OHRC) and LROC/PDS (NAC), with an explicit provenance
check built into the process this time (pixel scales must differ between
instruments; ground truth points must be manually verified; results are
sanity-checked against the Makharia et al. 2025 baseline before being
trusted in either direction).

---

## 4. What's proven vs. what's still open

**Proven:**
- The pipeline runs end-to-end, repeatably, without crashing (same site run
  twice produced consistent, non-flaky results).
- The ratio-correction relighting formula is numerically stable: no more
  saturation, no more divide-by-zero blowups, dynamic range under control.
- The validation harness itself is now honest — it no longer conflates
  RANSAC-fit RMSE with fallback nearest-correspondence distance, and flags
  suspiciously-good results instead of accepting them uncritically.

**Still open:**
- Whether PRISM relighting genuinely improves matching on real lunar
  imagery — this is the actual deliverable and it is not yet demonstrated
  on trustworthy data.
- IIRS↔WAC pair (Part 5) — not attempted at all yet.
- Polar site (Part 5) — blocked on Backend A's Phase 3/Week 3 ingestion.
- Real Backend A pipeline wiring (Part 6) — hard blocked on their client
  library being live.
- The actual handoff artifacts (Part 7) for any site.

---

## 5. Dependencies

**Hard-blocked on Backend A:**
- Part 6 in full — cannot be done without `get_products_for_site()`,
  `get_dem()`, `get_spice_kernels()` being live.
- Polar site specifically within Part 5.

**Not blocked — can proceed independently:**
- IIRS↔WAC (equatorial) — downloadable directly, same as OHRC/NAC.
- Further real-data PRISM validation — manual downloads, zero dependency.
- Part 7's handoff mechanics — can be demonstrated using manually-downloaded
  real data while waiting on Backend A, pending Backend A confirming the
  `matched_point_sets` schema/insert helper.

**Needs Backend B (not A):**
- Part 2's open contract questions (coordinate space, relit-image storage
  location, `run_id` ownership) — should be confirmed explicitly, not
  assumed, before more handoff work is built on top of them.

---

## 6. Immediate next steps, in order

1. Get the real-data validation report back (OHRC + NAC + SLDEM2015,
   manually sourced, provenance-checked) and confirm honestly whether
   relighting helps.
2. If confirmed: move to Part 5's equatorial half (IIRS↔WAC) using the
   same manual-download approach — don't wait on Backend A.
3. In parallel: confirm Part 2's contract questions are actually locked
   with Backend B, not just assumed.
4. Ping Backend A now (if not already done) for an ETA on
   `get_products_for_site()` / `get_dem()` / `get_spice_kernels()` — Part 6
   cannot start without it, so early notice matters even though this track
   isn't blocked from other work in the meantime.
5. Hold Part 8 (fine-tuning) until Parts 1–7 are stable — premature before
   then, and explicitly flagged in the project brief as the first thing to
   cut under time pressure.

---

## 7. Honesty note for the team / judges

Every "too good" or "too bad" result in this track has been investigated
rather than accepted or hidden. That includes catching a false regression
caused by a metric mismatch, three real bugs in the relighting math, and
one implausibly perfect result that turned out to trace back to synthetic
test data rather than a genuine win. This is worth stating plainly in Q&A
if asked how confident the numbers are — the answer is: rigorously checked,
not yet finalized on real independent imagery, and the team will not present
a number it can't defend.
