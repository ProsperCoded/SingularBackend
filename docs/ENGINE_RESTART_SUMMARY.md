# PrintPUF Engine Restart Summary

This document summarizes the final engine shape, the main optimization stack, and the changes made over time. It is meant to be the handoff note for restarting backend integration from a clean base.

## Current Engine Shape

The engine is a pure processing layer. It does not own a database, HTTP API, or verdict persistence.

Public entry points:
- `engine.pipeline.generate_qr_only()`
- `engine.pipeline.enrol()`
- `engine.pipeline.extract_features()`

Current CLI entry points:
- `engine generate`
- `engine scan-qr`
- `engine enrol`
- `engine features`
- `engine verify`

Core runtime contract:
- `generate` emits one QR PNG per call.
- `enrol` accepts 3 scans by default and returns a single enrolment bundle for one product.
- `verify` compares one scan against one enrolment bundle and returns `pass`, `suspicious`, or `fail`.
- Batch and page generation were removed completely.

Environment variables:
- `PRINTPUF_ED25519_PRIVATE_KEY_PEM`
- `PRINTPUF_ED25519_PUBLIC_KEY_PEM`
- Legacy aliases are still accepted in the engine code, but new setups should use the canonical names above.

## How The Engine Works

### Generation

`generate_qr_only()` signs a placeholder 32-byte sketch and renders a printable QR PNG. The QR payload is a signed CBOR blob wrapped in a `printpuf://verify?data=...` URI.

### Enrolment

`enrol()` now expects multiple scans of the same printed tag. It:
- localizes the tag
- validates that the QR payload matches the requested `product_id`
- extracts per-scan vectors and hashes
- averages the primary vector across scans
- derives the LBP sketch from the primary region
- signs the real sketch and reissues the QR
- stores per-scan structural and color references in the bundle

### Verification

`verify` compares the current scan against the enrolment bundle using:
- the primary structural vector
- primary/support/canvas pHashes
- a lightweight color signature from the support patches

The current verdict policy is intentionally graded:
- `pass`
- `suspicious`
- `fail`

## Optimization Stack We Kept

The final engine still includes the robustness features that were recommended before the batch cleanup:

- `WeChatQRCode` first, then `QRCodeDetector` fallback
- QR payload decoding and strict product-id validation
- ArUco marker refinement
- ECC refinement when a payload template can be reconstructed
- CLAHE on the primary region
- multi-region preprocessing with `primary_region`, `support_region`, and `canvas`
- pHash on all three regions
- LBP on the primary region
- SIFT mean-pooled descriptors on the primary region
- MobileNetV2 embeddings on the primary region
- a separate lightweight color signature from the support patches

## What Changed Over Time

### 1. Repository bootstrap

- Added the dependency file and a concise README.
- Established the virtualenv and `uv` install workflow.
- Added the implementation guide and PRD for reference.

### 2. Stage 1 preprocessing

- Implemented the initial image preprocessor.
- Added manual artifact helpers so intermediate outputs could be written to `artifacts/manual/`.
- Confirmed that preprocessing output is not a QR generator output but a rectified crop of the tag.

### 3. QR generation and signing

- Implemented QR generation from signed CBOR payloads.
- Implemented Ed25519 signing and verification.
- Added env-backed key loading.

### 4. Structural feature stages

- Implemented pHash.
- Implemented LBP.
- Fixed the LBP bin-size bug so the histogram shape is stable.
- Implemented SIFT.
- Implemented MobileNetV2 extraction.
- Implemented vector concatenation and cosine similarity.

### 5. Pipeline orchestration

- Added `pipeline.py` as the public engine contract.
- Defined `GenerateResult`, `EnrolResult`, and `FeatureResult`.
- Added CLI commands for generation, enrolment, scanning, features, and verification.

### 6. Layout and split-region model

- Reworked preprocessing to align the full tag canvas.
- Split the tag into:
  - `primary_region`
  - `support_region`
  - `canvas`
- Preserved the grayscale-first verification path while allowing the support region to act as secondary evidence.

### 7. Batch and page experiment

- Added batch/page generation and batch enrolment temporarily.
- Built A4 sheet layout tests and manual page composition helpers.
- Later removed the entire batch/page concept because it was not needed for the final system.

### 8. Multi-scan enrolment restored

- Reintroduced multi-image enrolment for a single tag.
- Default enrolment count was set to 3 scans.
- Enrolment now averages vectors and stores per-scan references.
- The CLI `enrol` command again accepts repeated `--image` inputs.

### 9. Color-awareness fix

- A real false-positive case showed that grayscale-only structural scoring was too close for some tags.
- Added a lightweight color signature path based on the support patches.
- Integrated color into enrolment and verification.
- Removed backward compatibility for old bundles so re-enrolment is required.

### 10. Final verifier behavior

- The verifier now combines:
  - structural score
  - pHash gates
  - color distance
- Close cases can still be marked `suspicious` instead of being forced into a brittle pass/fail split.

## Important Integration Notes

If you are restarting backend integration:

- Re-enrol all products with the current engine before trusting verification results.
- Do not reuse old bundles; the current bundle schema includes color signatures.
- Backend code should treat the engine as stateless and pure.
- Backend owns:
  - persistence
  - user/product records
  - scan logs
  - first-scan vs repeat-scan policy
  - final business verdicts

## Manual CLI Examples

```bash
source .venv/bin/activate
export PYTHONPATH=src:.

engine generate --product-id product-123 --vendor-id vendor-abc --output artifacts/manual/tag.png
engine scan-qr --image artifacts/manual/tag.png
engine enrol \
  --image ~/Downloads/enrol-1.jpeg \
  --image ~/Downloads/enrol-2.jpeg \
  --image ~/Downloads/enrol-3.jpeg \
  --product-id product-123 \
  --vendor-id vendor-abc \
  --output-dir artifacts/manual/enrolments/product-123
engine verify --bundle artifacts/manual/enrolments/product-123/enrolment.json --image ~/Downloads/correct2.jpeg
```

## Verification State

The test suite is currently green. The final state used for this summary passed the repository tests after the color-aware changes were added.
