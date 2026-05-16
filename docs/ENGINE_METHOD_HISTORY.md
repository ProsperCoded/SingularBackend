# PrintPUF Engine Method History

## Scope

This file catalogs the distinct engine methods that were actually tried in code, based on:

- commit history and diffs in `backend/services/engine/*`
- verification-related API wiring in `backend/api/tags.py` and `backend/services/engine_adapter.py`
- local notes in `VERIFICATION_DEBUG_SUMMARY.md`

Included commits reviewed:

- `9e1ade7` `feat: implement full print-PUF engine service with feature extraction and verification pipelines`
- `ab46653` `refactor: remove LBP sketch functionality from pipeline and signer services`
- `a4b5c58` `feat: implement halftone pattern analysis and extend verification results with detailed engine metrics`
- `21bae9a` `chore: update authentication and suspicious composite score thresholds`

This is intentionally method-focused, not commit-message-focused. Several distinct verification ideas landed inside the same commit, so they are separated here by technique.

## Chronology

| Order | Method | First Seen | Advantage | Disadvantage |
| --- | --- | --- | --- | --- |
| 1 | QR-localized, perspective-corrected tag alignment with ArUco and ECC refinement | `9e1ade7` | Strong geometric normalization before feature extraction. | Good alignment does not by itself solve original-vs-photocopy discrimination. |
| 2 | `primary_region = qr_panel` fingerprint crop | `9e1ade7` | Stable, easy-to-localize region centered on the QR panel. | Overweights deterministic QR structure, so clean copies can still look highly similar. |
| 3 | CLAHE-enhanced grayscale primary crop | `9e1ade7` | Improves detection robustness and contrast consistency under uneven lighting. | Can flatten or normalize away the fine ink/noise signal that matters for print authenticity. |
| 4 | `INTER_AREA` resize for the main fingerprint crop | `9e1ade7` | Stable downsampling and low aliasing for general vision tasks. | Acts like a smoothing filter, which is bad when the target signal is high-frequency print texture. |
| 5 | Uniform LBP histogram on the main crop (`P=24`, `R=3`, `26` bins) | `9e1ade7` | Compact texture descriptor with some robustness to small capture variation. | Compresses away too much detail for subtle print-forensics differences. |
| 6 | SIFT mean descriptor on the main crop | `9e1ade7` | Adds some structural invariance across angle and scale changes. | Averaging collapses descriptor spread and removes most of the local discriminative structure. |
| 7 | MobileNetV2 embedding on the main crop | `9e1ade7` | Strong identity/semantic signal for “does this look like the enrolled tag layout”. | Tends to score photocopies highly because semantic structure survives copying. |
| 8 | Concatenate `LBP + SIFT + MobileNet` into one normalized cosine vector | `9e1ade7` | Simple single-score similarity path and easy enrol/verify storage. | MobileNet dominates the dimensionality, so texture evidence gets buried. |
| 9 | Multi-region pHash checks on `primary`, `support`, and `canvas` | `9e1ade7` | Cheap structural guardrail against gross mismatches and bad captures. | pHash is coarse and can still pass structurally faithful reproductions. |
| 10 | Camera-observed color signature v1 (`12`-dim patch descriptor) | `9e1ade7` | Adds a second modality beyond grayscale structure. | Highly unstable across lighting and camera white balance, causing repeated false failures. |
| 11 | Structural verdict merged with color verdict | `9e1ade7` | Better than using vector similarity alone because it combines multiple signals. | Produced confusing verdicts when structure and displayed score looked “good” but color failed. |
| 12 | LBP sketch embedded and signed into the QR payload | `9e1ade7` | Attempted to bind the physical texture signature into the signed QR data. | Added complexity and was not stable enough to keep in the live pipeline. |
| 13 | Removed LBP sketch from enrolment bundle and QR signing | `ab46653` | Simplified the payload and removed a brittle coupling point. | Lost one possible offline/authenticity binding mechanism. |
| 14 | `primary_region = content_rect` instead of QR panel only | `a4b5c58` | Expands the fingerprint area beyond the QR block so the signal is less purely structural. | Also introduces more capture variance because the region is larger and more heterogeneous. |
| 15 | Relaxed blur and contrast quality gates | `a4b5c58` | Reduced brittle rejections after widening the fingerprint region. | Makes the verifier more permissive toward marginal captures and potentially weaker evidence. |
| 16 | Reference-guided color signature v2 (`24`-dim) using generated-tag patches and white balance correction | `a4b5c58` | Much more principled than raw camera color, because it compares against known expected patches. | Still sensitive to print and capture drift, and it increased system complexity. |
| 17 | Halftone periodicity detector on RGB reference patches | `a4b5c58` | Specifically targets photocopy/reprint artifacts that structural features miss. | Another heuristic branch that still needs calibration against real scan distributions. |
| 18 | Exposed detailed verification metrics and composite-style debug payload | `a4b5c58` | Made the engine easier to inspect and debug in real use. | More metrics did not automatically make the actual verdict logic better calibrated. |
| 19 | Dual-stream preprocessing: CLAHE-capable finder path plus raw `texture_region` judge path | `a4b5c58` | Separates localization robustness from authenticity measurement, which is the right architectural move. | More moving parts and bundle compatibility work than the original single-crop pipeline. |
| 20 | Full LBP histogram on raw texture crop (`P=8`, `R=1`, `256` bins, `method='default'`) | `a4b5c58` | Preserves more micro-texture detail and is better matched to print discrimination. | More sensitive to noise and lighting variation if not paired with a stable crop/normalization strategy. |
| 21 | Global intensity normalization on the raw texture crop | `a4b5c58` | Handles overall brightness shifts without locally warping the texture pattern. | Does not fix severe local shadows or highly uneven illumination. |
| 22 | Laplacian sharpness scoring and sharpness-ratio comparison | `a4b5c58` | Cheap and effective for catching blur/photocopy softness that semantic features miss. | Sensitive to focus and motion blur from genuine rescans, so thresholds must be tuned carefully. |
| 23 | Texture-first weighted score with `LBP + sharpness + pHash`, and `vector` weight set to `0` | `a4b5c58` | Moves the verdict away from MobileNet dominance and toward print-specific evidence. | Still relies on hand-tuned thresholds rather than calibrated distributions. |
| 24 | Product ID mismatch check from the scanned QR during verification | `a4b5c58` | Adds a direct identity sanity check against verifying the wrong enrolled product. | Only checks product ID resolution, not full signature verification of the QR payload in the verdict path. |
| 25 | Legacy/current feature compatibility during verification | `a4b5c58` | Allows old enrolled bundles to keep working across feature schema changes. | Preserves historical complexity and makes the scoring path harder to reason about. |
| 26 | Lowered final composite verdict bands to `AUTHENTIC >= 70`, `SUSPICIOUS >= 50` | `21bae9a` | Better matches real-world rescans when the old bands were too strict. | If the lower-level gates are weak, lower cutoffs can hide discrimination problems instead of fixing them. |

## Method Details

### Preprocessing and Crop Strategy

| Method | Code Evidence | Advantage | Disadvantage |
| --- | --- | --- | --- |
| QR panel crop | `9e1ade7` `services/engine/preprocessor.py`, `services/engine/pipeline.py` | Stable and deterministic crop around the easiest part of the tag to localize. | Too close to a pure “same QR structure” test. |
| Full content crop | `a4b5c58` `services/engine/preprocessor.py` | Captures more non-QR texture and side-fragment evidence. | Adds more nuisance variation from capture geometry and lighting. |
| Finder CLAHE + raw judge split | `a4b5c58` `services/engine/preprocessor.py` | Keeps robust localization while preserving a raw authenticity signal. | Harder to debug because detection and judgement no longer use the same pixels. |
| `INTER_AREA` for main crop | `9e1ade7` | Good generic resize behavior. | Blurs away useful high-frequency texture. |
| `INTER_CUBIC` for texture crop | `a4b5c58` | Better preserves edge shape for the raw texture branch. | Can amplify noise if the crop itself is unstable. |

### Texture and Structure Features

| Method | Code Evidence | Advantage | Disadvantage |
| --- | --- | --- | --- |
| Uniform LBP (`26` bins) | `9e1ade7` `services/engine/lbp.py` | Compact and easy to compare across scans. | Too compressed for fine print-forensics cues. |
| Full LBP (`256` bins) | `a4b5c58` `services/engine/lbp.py` | Retains subtle local pattern differences. | Requires stronger normalization and better threshold calibration. |
| SIFT mean descriptor | `9e1ade7` `services/engine/sift.py` | Helps with structural repeatability. | Mean pooling throws away descriptor variance, which may be the more useful signal. |
| MobileNetV2 embedding | `9e1ade7` `services/engine/mobilenet.py` | Strong “same tag class/layout” signal. | Weak for deciding original print vs photocopy. |
| Multi-region pHash | `9e1ade7` `services/engine/phash.py` | Cheap first-pass structural consistency check. | Not fine-grained enough for print authenticity by itself. |
| Halftone periodicity | `a4b5c58` `services/engine/halftone.py` | Directly targets photocopy-style periodic artifacts. | Another heuristic that can drift without a representative sample set. |
| Laplacian sharpness | `a4b5c58` `services/engine/preprocessor.py` and `services/engine/bundle.py` | Effective proxy for copy softness and blur. | Genuine shaky scans can look fake if thresholds are too aggressive. |

### Scoring and Verdict Logic

| Method | Code Evidence | Advantage | Disadvantage |
| --- | --- | --- | --- |
| Single fused cosine on concatenated vector | `9e1ade7` `services/engine/vector.py` and `services/engine/bundle.py` | Very simple scoring model. | Buries the print-specific signal under high-dimensional semantic features. |
| Structural thresholds `0.990 / 0.985` style | `9e1ade7` `services/engine/bundle.py` | Easy to reason about on paper. | Unrealistically strict for real phone rescans. |
| Structural + color merged verdict | `9e1ade7` `services/engine/bundle.py` | Better than trusting one branch alone. | Made the UI and verdict feel contradictory when color was unstable. |
| Texture-first weighted score | `a4b5c58` `services/engine/bundle.py` | Correctly shifts the decision center toward texture and sharpness. | Still hand-tuned, so the current numbers are guesses until calibrated on real samples. |
| Final score bands lowered to `70 / 50` | `21bae9a` `services/engine/bundle.py` | More forgiving on genuine rescans. | Can paper over unresolved feature-quality issues if used too early. |

### Identity and Binding

| Method | Code Evidence | Advantage | Disadvantage |
| --- | --- | --- | --- |
| Signed QR payload with embedded LBP sketch | `9e1ade7` `services/engine/signer.py`, `services/engine/pipeline.py`, `services/engine/lbp.py` | Strong idea for binding physical texture to the signed identity artifact. | Operationally brittle and removed shortly after launch. |
| Signed QR payload without LBP sketch | `ab46653` `services/engine/signer.py`, `services/engine/pipeline.py` | Simpler payload and fewer unstable moving parts. | Loses one authenticity-binding path and leaves the QR mostly identity-only. |
| Product ID mismatch guard during verify | `a4b5c58` `services/engine/bundle.py` | Prevents comparing a scan against the wrong enrolled product. | Not a substitute for full payload signature validation in the live verdict path. |

## What Changed The Most

The largest strategic swings were:

1. `qr_panel` fingerprinting to `content_rect` fingerprinting.
2. CLAHE-enhanced single-stream judging to dual-stream raw-texture judging.
3. `26`-bin uniform LBP to `256`-bin full LBP.
4. vector-dominant scoring to texture-first weighted scoring.
5. raw camera color checking to reference-guided color checking.
6. no photocopy-specific detector to explicit halftone and sharpness heuristics.
7. strict fixed similarity thresholds to lower composite-score bands.

## Short Read

If the question is "what big circles did I go through?", the main loops were:

- **Structure-first loop:** QR-panel crop, CLAHE, fused vector, strict similarity thresholds.
- **Wider-signal loop:** content-area crop, relaxed quality gates, more diagnostics.
- **Color-fix loop:** moved from camera-only patch color to reference-guided patch color.
- **Photocopy-detection loop:** added halftone, raw texture LBP, and sharpness ratio.
- **Threshold loop:** shifted from ultra-strict structural cutoffs to lower composite verdict bands.

## Caution For The Next Phase

The current codebase has tried many heuristics, but most thresholds are still empirical guesses. The next calibration pass should treat:

- genuine rescans
- photocopies
- screenshots
- reprints
- wrong enrolled product scans

as separate classes and measure each method against them directly instead of tuning by intuition.
