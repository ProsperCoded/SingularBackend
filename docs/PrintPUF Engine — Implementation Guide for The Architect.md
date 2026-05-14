# PrintPUF Engine — Implementation Guide for The Architect

This document is an AI-agent-ready implementation guide. Each stage is self-contained, defines exact inputs and outputs, and can be handed directly to Codex or Cursor as a scoped task. The engine is purely functional — no database calls, no HTTP, no external side effects. It receives data, processes it, and returns a result. Everything else (storage, API routing, webhooks) is owned by The Backbone.

***

## Project Structure

Use the `src/` layout. This prevents accidental imports and keeps test infrastructure clean.

```
printpuf-engine/
├── src/
│   └── engine/
│       ├── __init__.py
│       ├── generator.py         # Stage 1: QR code generation
│       ├── signer.py            # Stage 2: Ed25519 signing for QR payload
│       ├── layout.py            # Shared geometry for QR panel and support fragments
│       ├── preprocessor.py      # Stage 3: full-tag alignment and region splitting
│       ├── phash.py             # Stage 4: multi-region perceptual hash pre-filter
│       ├── lbp.py               # Stage 5: LBP texture extraction
│       ├── sift.py              # Stage 6: SIFT keypoint extraction
│       ├── mobilenet.py         # Stage 7: MobileNetV2 deep embedding
│       ├── vector.py            # Stage 8: concatenation, L2 norm, cosine sim
│       └── pipeline.py          # Stage 9: generate_qr_only, enrol, extract_features
├── tests/
│   ├── conftest.py              # Shared fixtures: test images, enrolled vectors
│   ├── test_preprocessor.py
│   ├── test_phash.py
│   ├── test_lbp.py
│   ├── test_sift.py
│   ├── test_mobilenet.py
│   ├── test_vector.py
│   ├── test_signer.py
│   ├── test_generator.py
│   ├── test_pipeline.py         # Integration test: generate → enrol → verify
├── test_images/
│   ├── enrolled_tag.jpg         # A printed + photographed tag (ground truth)
│   ├── rescan_tag.jpg           # Same physical tag, re-photographed
│   ├── screenshot_tag.jpg       # Screenshot of the tag on a screen
│   └── reprint_tag.jpg          # Same file printed again on a new sheet
├── pyproject.toml
├── .env.example
└── README.md
```

***

## Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
  "opencv-contrib-python>=4.9.0",  # SIFT requires contrib build
  "scikit-image>=0.22.0",
  "numpy>=1.26.0",
  "scipy>=1.12.0",
  "Pillow>=10.3.0",
  "imagehash>=4.3.0",
  "torch>=2.2.0",
  "torchvision>=0.17.0",
  "qrcode[pil]>=7.4.2",
  "cryptography>=42.0.0",
  "cbor2>=5.6.0",
  "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0", "pytest-cov", "Pillow"]
```

> **Note on OpenCV:** Install `opencv-contrib-python`, not `opencv-python`. SIFT lives in the `contrib` module. The two packages conflict — never install both.

***

## Stage 1 — QR Generator (`generator.py`)

**Purpose:** Generate a print-ready QR code PNG from a signed CBOR payload. This is called when a single tag is produced and again during enrolment when the real LBP sketch is available. The function itself is identical in both cases; what differs is the payload it receives.

**QR content format:**
```
printpuf://verify?data=<base64url-encoded CBOR payload>
```

The `printpuf://` scheme lets the consumer PWA distinguish a product tag from a vendor tag (`printpuf://vendor?id=...`) immediately on decode, before any server call.

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `cbor_payload` | `bytes` | Output from `sign_payload()` |
| `product_id` | `str` | Used to set QR alt text / metadata |
| `box_size` | `int` | Pixel size of each QR module. Default: `7` |
| `border` | `int` | White border in modules. Default: `4` |

**Output:** `bytes` — PNG image of the QR code, ready to write to disk or upload to Spaces.

**Codex instruction:**
> Create `src/engine/generator.py`. Write `generate_qr(cbor_payload: bytes, product_id: str, box_size: int = 7, border: int = 4) -> bytes`. Base64url-encode the cbor payload with `base64.urlsafe_b64encode(cbor_payload).decode()`. Build the URI string `f"printpuf://verify?data={encoded}"`. Create `qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=border)`. Call `qr.add_data(uri)`, `qr.make(fit=True)`. Render with `qr.make_image(fill_color='black', back_color='white')`. Save to a `BytesIO` buffer as PNG and return `buffer.getvalue()`.

> Use `ERROR_CORRECT_M` instead of `H`. In practice the signed CBOR payload already pushes the QR version high; lowering density improves phone-camera detection on printed labels while `box_size=7` keeps the physical symbol large enough for reliable printing and scanning.

***

## Stage 2 — Ed25519 Signer (`signer.py`)

**Purpose:** Sign the LBP sketch + product ID with an Ed25519 private key and encode the result as a CBOR binary payload. This payload is embedded in the QR code and allows the consumer app to verify authenticity offline without calling the server.

**Why Ed25519:** It is the recommended algorithm from the `cryptography` library for new projects — fast, small signatures (64 bytes), and safe against timing attacks. The private key stays on the server. The public key is baked into the consumer PWA at deploy time.

**Payload structure (CBOR-encoded):**

| Field | Type | Description |
|---|---|---|
| `pid` | `str` | Product ID |
| `vid` | `str \| None` | Vendor ID |
| `sketch` | `bytes` | 32-byte LBP sketch from Stage 5 |
| `sig` | `bytes` | 64-byte Ed25519 signature over `pid + vid + sketch` |

**Input parameters for `sign_payload`:**

| Parameter | Type | Description |
|---|---|---|
| `product_id` | `str` | Unique product identifier |
| `vendor_id` | `str \| None` | Vendor identifier, may be None |
| `lbp_sketch` | `bytes` | 32-byte sketch from `compute_lbp_sketch()` |
| `private_key_pem` | `bytes` | Ed25519 private key in PEM format, loaded from environment variable |

**Output:** `bytes` — CBOR-encoded payload, ready to embed in QR code data URI.

**Codex instruction:**
> Create `src/engine/signer.py`. Write two functions: (1) `sign_payload(product_id: str, vendor_id: str | None, lbp_sketch: bytes, private_key_pem: bytes) -> bytes` — load the PEM key with `serialization.load_pem_private_key(private_key_pem, password=None)`, validate that it is an `Ed25519PrivateKey`, compute `message = product_id.encode() + (vendor_id or '').encode() + lbp_sketch`, call `private_key.sign(message)` to get the 64-byte signature, encode the dict `{'pid': product_id, 'vid': vendor_id, 'sketch': lbp_sketch, 'sig': signature}` with `cbor2.dumps()`, and return the bytes. (2) `verify_payload(cbor_bytes: bytes, public_key_pem: bytes) -> dict` — decode CBOR, load the PEM public key with `serialization.load_pem_public_key(public_key_pem)`, reconstruct the message, call `public_key.verify(sig, message)` (raises `InvalidSignature` if tampered), and return the decoded dict on success.

***

## Stage 3 — Preprocessor (`preprocessor.py`)

**Purpose:** Load any image source (file path, bytes, numpy array), rectify the full tag canvas using the QR panel as the alignment anchor, and split the tag into fixed verification regions. This replaces the old single-anchor model with a multi-region model:

- a **primary region**: the QR-panel crop, treated with the strict fingerprint pipeline
- a **support region**: the left fragment column, treated with looser grayscale checks
- a **canvas**: the full aligned grayscale tag image, used for coarse whole-tag consistency checks

**Why CLAHE:** Contrast Limited Adaptive Histogram Equalisation normalises local contrast without washing out the micro-texture that LBP and SIFT depend on. A standard histogram equalisation would homogenise the very signal we're trying to measure.

**Why split the image:** The strict and loose regions do not behave equally under real capture conditions. The QR panel and adjacent fingerprint area are more stable and should feed the main vector pipeline. The left fragment column is intentionally more variable and should be used as supporting evidence rather than primary truth.

**Alignment model:** The QR code corners provide the initial homography. ArUco fiducials in the generated tag corners then refine the geometry on the warped canvas, and if the QR payload decodes the preprocessor regenerates the exact template and runs a final ECC refinement step. From that aligned canvas, the preprocessor crops:

- `primary_region`: the QR panel area, resized to `256 × 256`, greyscale, CLAHE-applied when enabled
- `support_region`: the left fragment column, resized to `256 × 256`, greyscale, no CLAHE by default
- `canvas`: the full aligned greyscale tag image at its natural canvas size

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `image_source` | `str \| bytes \| np.ndarray` | File path, raw bytes from upload, or already-loaded array |
| `anchor_size` | `int` | Output size of each square verification region. Default: `256` |
| `apply_clahe` | `bool` | Whether to apply CLAHE to `primary_region`. Default: `True`. |

**Output of `preprocess_tag()`:** `PreprocessedTag` dataclass with:

| Field | Type | Description |
|---|---|---|
| `canvas` | `np.ndarray` | Full aligned greyscale tag image, dtype `uint8` |
| `primary_region` | `np.ndarray` | Shape `(256, 256)`, dtype `uint8` |
| `support_region` | `np.ndarray` | Shape `(256, 256)`, dtype `uint8` |
| `payload_uri` | `str \| None` | Decoded QR URI when available |
| `alignment_method` | `str` | Detector / refinement chain used |
| `quality` | `TagQuality` | Basic quality metrics for blur, contrast, size, and refinement |

**Compatibility wrapper:** `preprocess()` remains as a convenience wrapper that returns `preprocess_tag(...).primary_region` so existing single-region calls continue to work during migration.

**Optional helper:** `extract_reference_patches()` may return RGB crops of the individual red, green, and blue fragments for diagnostics, calibration, and the lightweight color-aware verifier.

**Codex instruction:**
> Create `src/engine/preprocessor.py`. Define `LocalizationError`, `ImageQualityError`, `TagQuality`, and `PreprocessedTag`. Write `preprocess_tag(image_source, anchor_size=256, apply_clahe=True) -> PreprocessedTag`. It must: (1) accept a file path string, raw bytes, or existing numpy array as `image_source`; (2) load/convert to a BGR numpy array using OpenCV; (3) localize the QR code corners with a robust priority order: `cv2.wechat_qrcode_WeChatQRCode().detectAndDecode()` first, then `cv2.QRCodeDetector()` fallback methods; (4) compute an initial homography from the QR panel; (5) refine the warped canvas with ArUco corner markers when they are detected; (6) when the QR payload decodes into a valid engine payload, regenerate the exact template image and run `cv2.findTransformECC()` as a final alignment refinement; (7) reject obviously poor captures with a clear quality error rather than silently extracting unstable crops; (8) convert the final aligned image to greyscale; (9) crop the QR panel as `primary_region` and resize it to `anchor_size × anchor_size`; (10) crop the left support fragment column as `support_region` and resize it to `anchor_size × anchor_size`; (11) if `apply_clahe` is True, apply `cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))` to `primary_region`; (12) return the `PreprocessedTag`. Also keep `preprocess()` as a wrapper returning `preprocess_tag(...).primary_region`. Add `extract_reference_patches()`, `decode_qr_payload()`, and `decode_qr_payload_bytes()`.

***

## Stage 4 — pHash Pre-filter (`phash.py`)

**Purpose:** Compute coarse perceptual hashes across the aligned tag representation. pHash remains the first comparison step in verification, but now it is applied to multiple regions instead of only one crop:

- `canvas_hash`: full aligned tag image, used as a coarse whole-tag sanity check
- `primary_hash`: strict hash for the QR-panel region
- `support_hash`: looser hash for the support fragment column

**How it works internally:** The `imagehash.phash()` function resizes the input to 32×32, converts to greyscale, applies a 2D Discrete Cosine Transform (DCT), retains the top-left 8×8 block of DCT coefficients (the low-frequency structural information), computes the median of those 64 values, and assigns `1` to each value above the median and `0` below. The result is a 64-bit integer. Comparison uses Hamming distance — the count of differing bit positions between two hashes.

**Threshold philosophy:**

- `primary_hash` uses the stricter threshold: Hamming distance ≤ `10`
- `support_hash` uses a looser threshold because the support region is more sensitive to camera and print variation
- `canvas_hash` is a coarse whole-image guardrail rather than a hard truth source
- only the `primary_hash` should be treated as a hard reject gate in the default CLI flow; support and canvas hashes remain advisory, while a lightweight color signature from the support patches acts as a secondary tie-breaker

This stage is intentionally conservative. pHash rejects obvious structural mismatch and low-quality garbage before the more expensive feature extractors run.

**Input parameters for `compute_phash`:**

| Parameter | Type | Description |
|---|---|---|
| `image_array` | `np.ndarray` | Any greyscale image region or full canvas |

**Output of `compute_phash`:** `str` — hex-encoded 64-bit hash (16 hex characters).

**Input parameters for `compute_region_phashes`:**

| Parameter | Type | Description |
|---|---|---|
| `preprocessed_tag` | `PreprocessedTag` | Output from `preprocess_tag()` |

**Output of `compute_region_phashes`:** `RegionPHash` dataclass with:

| Field | Type | Description |
|---|---|---|
| `canvas_hash` | `str` | Full-tag pHash |
| `primary_hash` | `str` | Strict region pHash |
| `support_hash` | `str` | Support region pHash |

**Codex instruction:**
> Create `src/engine/phash.py`. Define `RegionPHash` with `canvas_hash`, `primary_hash`, and `support_hash`. Write three functions: (1) `compute_phash(image_array: np.ndarray) -> str` — converts the numpy array to a PIL Image, calls `imagehash.phash()`, and returns `str(hash)`; (2) `compare_phash(hash_a: str, hash_b: str) -> int` — converts both hex strings back to imagehash objects using `imagehash.hex_to_hash()` and returns the Hamming distance; (3) `compute_region_phashes(preprocessed_tag: PreprocessedTag) -> RegionPHash` — computes hashes for the full canvas, primary region, and support region. Add module-level constants `PHASH_THRESHOLD = 10` and `SUPPORT_PHASH_THRESHOLD = 16`.

***

## Stage 5 — LBP Texture Extraction (`lbp.py`)

**Purpose:** Extract a rotation-invariant texture histogram from the **primary region**. This remains the primary defence against screenshot attacks — a screenshot has no physical ink texture and will produce a completely different histogram from a genuine print.

**How it works internally:** For each pixel in the 256×256 greyscale image, `local_binary_pattern()` examines its `P` circularly distributed neighbours at radius `R`. For each neighbour, it writes `1` if the neighbour's intensity ≥ centre pixel intensity, else `0`, producing a `P`-bit binary code. With `method='uniform'`, only patterns with at most 2 transitions between 0 and 1 in the circular bit sequence are kept as distinct values (there are `P*(P-1)+3` of them), and all non-uniform patterns are mapped to a single bin. This produces a histogram of `P*(P-1)+3` bins — the feature vector.

**Optimal parameters:** `P=24, R=3, method='uniform'`. With `skimage.feature.local_binary_pattern(..., method='uniform')`, this yields `P + 2 = 26` bins in practice. It captures texture at a scale that corresponds to the ink scatter grain size. Using `P=8, R=1` (common in tutorials) is too coarse for this application.

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `image_array` | `np.ndarray` | `preprocessed_tag.primary_region`, shape `(256, 256)`, uint8 |
| `P` | `int` | Number of neighbours. Default: `24` |
| `R` | `float` | Radius in pixels. Default: `3.0` |

**Output:** `np.ndarray` of shape `(26,)`, dtype `float32`. Normalised histogram — ready for concatenation.

**Support region note:** The support region does not feed LBP in the core pipeline. It is reserved for coarser, lower-weight checks because it is more sensitive to capture variance.

**Sketch for QR offline payload:** A 32-byte compressed LBP sketch is derived from the primary-region histogram by taking the top-16 most discriminative bins, quantising each to 2 bits (4 levels), and packing into 32 bytes. This is what gets embedded in the QR code.

**Codex instruction:**
> Create `src/engine/lbp.py`. Write: (1) `extract_lbp(image_array: np.ndarray, P: int = 24, R: float = 3.0) -> np.ndarray` — runs `skimage.feature.local_binary_pattern(image_array, P, R, method='uniform')`, sets `n_bins = int(lbp_image.max() + 1)`, builds a normalised histogram with `numpy.histogram(lbp_image.ravel(), bins=n_bins, range=(0, n_bins), density=True)`, and returns the histogram array as float32. (2) `compute_lbp_sketch(lbp_vector: np.ndarray) -> bytes` — takes the lbp histogram, selects the top 16 bins by magnitude, quantises each to 2 bits using `np.digitize` with 4 equal-width bins, and returns a fixed 32-byte sketch. A practical packing is 16 bytes of selected bin indices plus 16 bytes of quantised levels.

***

## Stage 6 — SIFT Keypoint Extraction (`sift.py`)

**Purpose:** Extract a compact descriptor from the structural landmarks in the **primary region**. SIFT is robust to rotation and scale, making it the best performer for matching the same physical print across different scan angles.

**How it works internally:** SIFT builds a Difference-of-Gaussians (DoG) scale-space pyramid by subtracting successive Gaussian-blurred versions of the image. Local extrema in this pyramid are candidate keypoints. Each keypoint gets an orientation assigned from the dominant gradient direction in its neighbourhood. Around each keypoint, a 4×4 grid of 8-bin gradient orientation histograms is computed, producing a 128-number descriptor vector per keypoint. For a `256 × 256` primary region, SIFT typically finds 80–200 keypoints.

**Aggregation into a fixed-size vector:** Individual keypoint descriptors vary in count per image. To produce a fixed-size feature for cosine comparison, aggregate by computing the **mean descriptor** across all detected keypoints (mean pooling). This produces a single 128-dimension vector regardless of keypoint count.

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `image_array` | `np.ndarray` | `preprocessed_tag.primary_region`, shape `(256, 256)`, uint8 |
| `n_features` | `int` | Max keypoints to retain. Default: `150` |
| `contrast_threshold` | `float` | Minimum keypoint contrast. Default: `0.03` |

**Output:** `np.ndarray` of shape `(128,)`, dtype `float32`. Mean-pooled SIFT descriptor, L2-normalised.

**Codex instruction:**
> Create `src/engine/sift.py`. Write `extract_sift(image_array: np.ndarray, n_features: int = 150, contrast_threshold: float = 0.03) -> np.ndarray`. Use `cv2.SIFT_create(nfeatures=n_features, contrastThreshold=contrast_threshold)`. Call `sift.detectAndCompute(image_array, None)` to get `(keypoints, descriptors)`. If `descriptors` is None or has fewer than 5 keypoints, return a zero vector `np.zeros(128, dtype=np.float32)`. Otherwise return `np.mean(descriptors, axis=0).astype(np.float32)`. Do not L2-normalise here — normalisation happens in Stage 6.

***

## Stage 7 — MobileNetV2 Deep Embedding (`mobilenet.py`)

**Purpose:** Produce a 1,280-dimension semantic embedding of the **primary region** using a pre-trained neural network. This layer is the most robust to real-world capture variation — changes in phone camera model, lighting colour temperature, and moderate angle shifts.

**How it works internally:** MobileNetV2 is loaded from `torchvision.models` with `weights=MobileNet_V2_Weights.DEFAULT` (ImageNet pre-trained). The final classification layer (`model.classifier`) is removed — only the feature extractor (`model.features` + adaptive average pool) is used. The output is a 1,280-dimension vector. The model is set to `eval()` mode and wrapped in `torch.inference_mode()` for performance. The primary region is resized to `224 × 224`, converted to a 3-channel tensor (repeating the greyscale channel three times), and normalised with ImageNet mean `[0.485, 0.456, 0.406]` and std `[0.229, 0.224, 0.225]`.

**Singleton pattern:** The model must be loaded once at module import time and reused for every call. Loading PyTorch models on every request adds 3–5 seconds of overhead. Use a module-level singleton.

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `image_array` | `np.ndarray` | `preprocessed_tag.primary_region`, shape `(256, 256)`, uint8 |

**Output:** `np.ndarray` of shape `(1280,)`, dtype `float32`.

**Codex instruction:**
> Create `src/engine/mobilenet.py`. At module level, load MobileNetV2: `model = torchvision.models.mobilenet_v2(weights=torchvision.models.MobileNet_V2_Weights.DEFAULT)`. Remove the classifier: `model.classifier = torch.nn.Identity()`. Call `model.eval()`. Write `extract_mobilenet(image_array: np.ndarray) -> np.ndarray`. Inside: (1) repeat greyscale channel to RGB: `rgb = np.stack([image_array]*3, axis=-1)`; (2) convert to PIL Image and apply `transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(), transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])])`; (3) add batch dimension with `.unsqueeze(0)`; (4) run `with torch.inference_mode(): features = model(tensor)`; (5) return `features.squeeze().numpy().astype(np.float32)`.

***

## Stage 8 — Vector Construction & Cosine Similarity (`vector.py`)

**Purpose:** Concatenate the three **primary-region** feature vectors into one combined vector, L2-normalise it, and provide the cosine similarity function used at verification time.

**Why L2-normalise:** After normalisation, cosine similarity between two vectors is equivalent to a simple dot product. It removes magnitude differences caused by variation in image brightness or keypoint count, leaving only directional (structural) similarity.

**Support-region policy:** The support region is intentionally **not** concatenated into this main vector. It should be scored with looser logic and lower weight than the primary fingerprint region, then fused later at the decision layer.

**Vector dimensions:**
| Source | Dimensions |
|---|---|
| LBP histogram | 26 |
| SIFT mean descriptor | 128 |
| MobileNetV2 embedding | 1,280 |
| **Combined** | **1,434** |

**Input parameters for `build_vector`:**

| Parameter | Type | Description |
|---|---|---|
| `lbp_vector` | `np.ndarray` | Shape `(26,)` from Stage 5 |
| `sift_vector` | `np.ndarray` | Shape `(128,)` from Stage 6 |
| `mobilenet_vector` | `np.ndarray` | Shape `(1280,)` from Stage 7 |

**Output of `build_vector`:** `np.ndarray` of shape `(1434,)`, dtype `float32`, L2-normalised.

**Input parameters for `cosine_similarity`:**

| Parameter | Type | Description |
|---|---|---|
| `vec_a` | `np.ndarray` | Enrolled vector, shape `(1434,)` |
| `vec_b` | `np.ndarray` | Query vector, shape `(1434,)` |

**Output of `cosine_similarity`:** `float` in range `[0.0, 1.0]`.

**Codex instruction:**
> Create `src/engine/vector.py`. Write two functions: (1) `build_vector(lbp_vector, sift_vector, mobilenet_vector) -> np.ndarray` — concatenates the three arrays with `np.concatenate`, divides by `np.linalg.norm(combined) + 1e-12` (the epsilon prevents division by zero on degenerate inputs), returns as float32; (2) `cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float` — since both inputs are already L2-normalised, this is `float(np.dot(vec_a, vec_b))`, clamped to `[0.0, 1.0]` with `np.clip`.

***

## Stage 9 — Pipeline Orchestrator (`pipeline.py`)

**Purpose:** The single public interface of the entire engine. The Backbone imports only from `pipeline.py`. Nothing else is imported externally. This stage exposes three functions corresponding to the three phases of the system lifecycle.

### The Two-Step Enrolment Flow

Batch generation and fingerprint enrolment are **separate operations**. This is the most important architectural clarification in the engine:

```
STEP 1 — GENERATE (no photo, called at payment time):
  Brand pays via Squad → Backbone calls generate_qr_only() × N
  → N signed QR PNGs delivered as ZIP
  → Brand prints the QR codes onto physical products

STEP 2 — ENROL (photo required, called after printing):
  Factory camera photographs each printed tag 3 times
  → Backbone calls enrol() with the 3 photos + product_id
  → Real fingerprint is aggregated across the scan set and stored in DB
  → Tag is now live and verifiable
```

For the hackathon, Step 2 is performed manually: print the tags, capture three clear photos per tag, and call `enrol()` once per tag.

***

### `generate_qr_only(product_id, vendor_id, private_key_pem) -> GenerateResult`

Generates a signed QR code without any image input. Uses a zero-filled placeholder sketch. Called once per tag by The Backbone or backend worker.

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `product_id` | `str` | Unique ID pre-generated by The Backbone |
| `vendor_id` | `str \| None` | Vendor this code is assigned to |
| `private_key_pem` | `bytes` | Ed25519 private key from environment |

**Output `GenerateResult` (dataclass):**

| Field | Type | Description |
|---|---|---|
| `product_id` | `str` | Echo of input |
| `qr_png_bytes` | `bytes` | Printable QR code PNG |

***

### `enrol(image_source, product_id, vendor_id, private_key_pem, required_scan_count=3) -> EnrolResult`

Runs fingerprint enrolment on photographs of an **already-printed** tag. Extracts the real microscopic fingerprint and returns it for storage. The Backbone stores the returned vector in pgvector.

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `image_source` | `str \| bytes \| np.ndarray \| Sequence[...]` | One or more photos of the printed tag |
| `product_id` | `str` | Must match the ID used in `generate_qr_only()` |
| `vendor_id` | `str \| None` | Vendor assignment |
| `private_key_pem` | `bytes` | Ed25519 private key from environment |
| `required_scan_count` | `int` | Minimum number of enrolment scans. Default: `3` |
**Output `EnrolResult` (dataclass):**

| Field | Type | Description |
|---|---|---|
| `product_id` | `str` | Echo of input |
| `combined_vector` | `np.ndarray` | Mean primary-region vector to store in pgvector |
| `combined_vectors` | `tuple[np.ndarray, ...]` | Per-scan vectors for secondary scoring |
| `primary_phash_str` | `str` | Representative strict pHash for the primary region |
| `primary_phash_strs` | `tuple[str, ...]` | Per-scan primary pHashes |
| `support_phash_str` | `str` | Representative looser pHash for the support region |
| `support_phash_strs` | `tuple[str, ...]` | Per-scan support pHashes |
| `canvas_phash_str` | `str` | Representative coarse whole-tag pHash |
| `canvas_phash_strs` | `tuple[str, ...]` | Per-scan canvas pHashes |
| `lbp_sketch` | `bytes` | 32-byte sketch derived from the averaged LBP vector |
| `updated_qr_png_bytes` | `bytes` | Re-issued QR with real sketch embedded (optionally reprint) |
| `scan_count` | `int` | Number of enrolment scans used |

***

### `extract_features(image_source) -> FeatureResult`

Runs feature extraction on a consumer's camera image at verification time. Returns the query vector for The Backbone to compare against the enrolled vector using pgvector. **No comparison happens inside the engine.**

**Input parameters:**

| Parameter | Type | Description |
|---|---|---|
| `image_source` | `str \| bytes \| np.ndarray` | Camera image submitted by consumer |

**Output `FeatureResult` (dataclass):**

| Field | Type | Description |
|---|---|---|
| `combined_vector` | `np.ndarray` | Shape `(1434,)` — primary-region vector to compare against enrolled vector |
| `primary_phash_str` | `str` | Strict pHash for the primary region |
| `support_phash_str` | `str` | Looser pHash for the support region |
| `canvas_phash_str` | `str` | Coarse whole-tag pHash |

***

**Codex instruction:**
> Create `src/engine/pipeline.py`. Import all stage modules. Define three dataclasses: `GenerateResult`, `EnrolResult`, and `FeatureResult` with the fields listed above. 
>
> Write `generate_qr_only(product_id, vendor_id, private_key_pem) -> GenerateResult`: create a 32-byte zero placeholder sketch `b'\x00' * 32`, call `signer.sign_payload(product_id, vendor_id, placeholder_sketch, private_key_pem)`, call `generator.generate_qr(cbor_payload, product_id)`, return `GenerateResult`. 
>
> Write `enrol(image_source, product_id, vendor_id, private_key_pem) -> EnrolResult`: preprocess the single image, confirm the decoded payload `pid` matches `product_id`, compute pHashes and vectors, derive the LBP sketch from the primary region, sign it, regenerate the QR, and return the reference data.
>
> Write `extract_features(image_source) -> FeatureResult`: call `preprocess_tag()` → `compute_region_phashes()` → LBP/SIFT/MobileNet on `primary_region` → `vector.build_vector()`, assemble and return `FeatureResult`. 
>
> None of these functions perform any I/O. No database calls. No HTTP calls. Pure computation in, structured result out. The support region must be preserved in the preprocessing and pHash path even when later vector stages focus on the primary region.

***

## Stage 11 — Optional Color Anti-Clone Layer

**Purpose:** Add a deliberately color-variant print layer around or adjacent to the QR/tag region so that reprints accumulate printer-specific color drift, ink spread, halftone differences, and paper absorption artifacts. This stage is **optional** and is not part of the core engine contract.

**Why it exists:** Pure black-and-white QR labels are easy to reproduce mechanically. Even when the payload is signed, a cloned print of the visible tag can look nearly perfect to the eye. A constrained multi-palette layer can introduce extra physical instability across reprints, especially when different printers, inks, media, or rendering pipelines are used.

**Important limitation:** Color by itself is **not security** unless the engine measures it. The current verifier now includes a lightweight color signature derived from the support patches, but the main vector path remains grayscale-first. That means color helps break close ties and washed-out reprints, but it does not replace the primary structural fingerprint.

### Recommended design use

- Keep the QR code itself standards-safe and easily scannable.
- Put the color layer in a controlled sideband region, border, gutter, frame, or anchor-adjacent strip rather than inside the QR modules unless QR readability has been validated thoroughly.
- Use a small fixed palette, such as 3 controlled colors, instead of unrestricted gradients.
- Reuse the same geometric layout at enrolment and verification so color drift is measured against a stable template.
- Treat this as an augmentation layer on top of the signed QR + fingerprint system, not a replacement.

### Tradeoffs

- **Pros**
  - Raises the difficulty of visually convincing reprints.
  - Introduces printer, substrate, and ink variability that simple binary reproduction may not preserve exactly.
  - Can make counterfeit production more operationally expensive.

- **Cons**
  - Phone cameras introduce white-balance, exposure, HDR, and compression shifts that can swamp genuine color differences.
  - Ambient lighting changes color more aggressively than grayscale texture.
  - Low-end printing or faded labels may increase false rejects.
  - If color sits too close to QR timing/finder structures, scan reliability can degrade.
  - If the engine still converts to grayscale, most of the benefit remains unmeasured.

### When to avoid it

- Avoid it for the first production-grade engine milestone if robustness and low false rejects matter more than clone resistance.
- Avoid it when tags will be scanned in uncontrolled lighting, with low-end cameras, or on heavily reflective packaging.
- Avoid embedding color complexity directly into QR modules unless scanner tolerance has been validated across devices and print vendors.
- Avoid using it as the only anti-counterfeit mechanism. It should sit behind signed payloads and physical fingerprinting, not replace them.

### Recommendations

1. Keep the current grayscale-first engine as the default baseline.
2. If the color layer is used now, treat it as a visual hardening layer only.
3. Keep the current color-aware path narrow and support-region-focused instead of pushing color into the QR panel itself.
4. The clean extension remains a separate module, for example `color_features.py`, that extracts stable color statistics from a fixed sideband region.
5. Recommended first measurements for a future version:
   - Per-channel mean and variance in a fixed color band
   - Small normalized color histograms in Lab or HSV space
   - Channel-ratio features that are less sensitive to global brightness
6. Only enable color-based acceptance logic after collecting real scans across:
   - multiple printers
   - multiple phones
   - indoor and daylight conditions
   - original prints vs reprints

### Non-goal for the current implementation

Stage 11 does **not** change the current core engine API, thresholds, or grayscale preprocessing path. It is an optional design direction for future hardening once baseline enrolment and verification are stable.

***

## Testing in Isolation

The engine is tested entirely independently of the backend. Four physical test images cover all scenarios.

### `tests/conftest.py` — Shared Fixtures

```python
import pytest
import numpy as np
from pathlib import Path

IMAGES = Path(__file__).parent.parent / "test_images"

@pytest.fixture(scope="session")
def enrolled_image():
    return str(IMAGES / "enrolled_tag.jpg")

@pytest.fixture(scope="session")
def rescan_image():
    return str(IMAGES / "rescan_tag.jpg")

@pytest.fixture(scope="session")
def screenshot_image():
    return str(IMAGES / "screenshot_tag.jpg")

@pytest.fixture(scope="session")
def reprint_image():
    return str(IMAGES / "reprint_tag.jpg")

@pytest.fixture(scope="session")
def enrolled_vector(enrolled_image):
    from engine.pipeline import extract_features
    return extract_features(enrolled_image).combined_vector
```

### Test Contracts Per Stage

**`test_preprocessor.py`**
- `preprocess()` output shape is exactly `(256, 256)`
- `preprocess()` output dtype is `uint8`
- `preprocess_tag()` returns `canvas`, `primary_region`, and `support_region`
- `primary_region` and `support_region` are both `(256, 256)` `uint8`
- Calling with a bytes input produces the same primary-region shape as calling with a file path
- `extract_reference_patches()` returns the three RGB fragment crops for diagnostics

**`test_phash.py`**
- `compute_phash` returns a 16-character hex string
- Hamming distance between same image encoded twice = 0
- `compute_region_phashes()` returns `canvas_hash`, `primary_hash`, and `support_hash`
- `SUPPORT_PHASH_THRESHOLD` is looser than `PHASH_THRESHOLD`
- `compare_phash(enrolled_primary_phash, screenshot_primary_phash)` > `PHASH_THRESHOLD`

**`test_lbp.py`**
- Output shape is `(26,)` for default `P=24`
- Output sums to approximately 1.0 (normalised histogram)
- LBP vector from `enrolled_image` vs `screenshot_image`: cosine similarity < 0.6

**`test_sift.py`**
- Output shape is `(128,)`
- Returns zero vector when fed a blank white image (no keypoints)
- SIFT vector from `enrolled_image` vs `reprint_image`: cosine similarity < 0.7

**`test_mobilenet.py`**
- Output shape is `(1280,)`
- Output dtype is `float32`
- Model is a singleton — calling twice does not re-load weights (assert `id(model)` is same)

**`test_vector.py`**
- `build_vector` output shape is `(1434,)`
- L2 norm of output is approximately 1.0 (unit vector)
- `cosine_similarity(v, v)` = 1.0 for any vector `v`
- `cosine_similarity(zeros, zeros)` does not raise

**`test_pipeline.py` — Integration Tests (most important)**

```python
THRESHOLDS = {"authentic": 0.92, "suspicious_low": 0.75}

def test_authentic_rescan(enrolled_vector, rescan_image):
    from engine.pipeline import extract_features
    from engine.vector import cosine_similarity
    query = extract_features(rescan_image).combined_vector
    score = cosine_similarity(enrolled_vector, query)
    assert score >= THRESHOLDS["authentic"], f"Authentic rescan scored {score:.3f}"

def test_screenshot_rejected(enrolled_vector, screenshot_image):
    from engine.pipeline import extract_features
    from engine.vector import cosine_similarity
    query = extract_features(screenshot_image).combined_vector
    score = cosine_similarity(enrolled_vector, query)
    assert score < THRESHOLDS["suspicious_low"], f"Screenshot scored {score:.3f} — not rejected"

def test_reprint_rejected(enrolled_vector, reprint_image):
    from engine.pipeline import extract_features
    from engine.vector import cosine_similarity
    query = extract_features(reprint_image).combined_vector
    score = cosine_similarity(enrolled_vector, query)
    assert score < THRESHOLDS["suspicious_low"], f"Reprint scored {score:.3f} — not rejected"
```

Run with: `pytest tests/ -v --tb=short`

***

## Environment Variables

```bash
# .env.example
PRINTPUF_ED25519_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
PRINTPUF_ED25519_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
```

The engine reads the canonical `PRINTPUF_ED25519_*` variables. The shorter
`PRINTPUF_PRIVATE_KEY_PEM` and `PRINTPUF_PUBLIC_KEY_PEM` aliases remain
supported for backward compatibility, but new setups should use the canonical
names above.

Generate a keypair once:
```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

key = Ed25519PrivateKey.generate()
print(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode())
print(key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode())
```

The public key PEM is also hardcoded into the consumer PWA for offline payload verification.

***

## Handoff Contract to The Backbone

The Backbone imports from two engine modules only:

```python
from engine.pipeline import generate_qr_only, enrol, extract_features
from engine.pipeline import GenerateResult, EnrolResult, FeatureResult
```

**`generate_qr_only()` returns:** `GenerateResult`, which contains the QR PNG bytes for one tag. If the backend needs multiple tags, it calls the function repeatedly and stores the resulting byte strings itself.

**`enrol()` returns:** `EnrolResult` with `combined_vector`, `combined_vectors`, `primary_phash_str`, `primary_phash_strs`, `support_phash_str`, `support_phash_strs`, `canvas_phash_str`, `canvas_phash_strs`, `lbp_sketch`, `updated_qr_png_bytes`, and `scan_count`. The Backbone stores the primary-region vector in pgvector, stores the per-scan references for diagnostics and secondary scoring, updates the product record from `pending_enrolment` to `enrolled`, and optionally replaces the QR image in Spaces with the re-issued version containing the real sketch.

**`extract_features()` returns:** `FeatureResult` with `combined_vector`, `color_signature`, `primary_phash_str`, `support_phash_str`, and `canvas_phash_str`. The Backbone runs pgvector cosine comparison on the primary-region vector, applies a hard pHash gate to the primary region, and can use the color signature from the support patches as a secondary anti-clone signal. The engine never knows the result of its own comparison.

The verdict logic — threshold application and append-only scan event logging — belongs entirely to The Backbone. Verification never deletes or consumes the underlying tag record.
