from __future__ import annotations

import numpy as np

from engine.generator import generate_qr
from engine.lbp import compute_lbp_sketch, extract_lbp
from engine.preprocessor import preprocess_tag
from scripts.manual_artifacts import save_bytes


def test_extract_lbp_returns_expected_shape_for_default_parameters() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)

    lbp_vector = extract_lbp(image)

    assert lbp_vector.shape == (26,)
    assert lbp_vector.dtype == np.float32


def test_extract_lbp_histogram_sums_to_one() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)

    lbp_vector = extract_lbp(image)

    assert np.isclose(float(lbp_vector.sum()), 1.0, atol=1e-4)


def test_extract_lbp_returns_fixed_shape_for_low_entropy_input() -> None:
    image = np.zeros((256, 256), dtype=np.uint8)

    lbp_vector = extract_lbp(image)

    assert lbp_vector.shape == (26,)
    assert np.isclose(float(lbp_vector.sum()), 1.0, atol=1e-4)


def test_compute_lbp_sketch_returns_fixed_32_byte_output() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)
    lbp_vector = extract_lbp(image)

    sketch = compute_lbp_sketch(lbp_vector)

    assert isinstance(sketch, bytes)
    assert len(sketch) == 32


def test_compute_lbp_sketch_is_deterministic() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-123")
    primary_region = preprocess_tag(png_bytes).primary_region
    lbp_vector = extract_lbp(primary_region)

    sketch_a = compute_lbp_sketch(lbp_vector)
    sketch_b = compute_lbp_sketch(lbp_vector)

    assert sketch_a == sketch_b


def test_lbp_output_can_be_saved_for_manual_inspection() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)
    lbp_vector = extract_lbp(image)

    output_path = save_bytes(lbp_vector.tobytes(), "lbp-stage5-test.bin")

    assert output_path.exists()
    assert output_path.read_bytes() == lbp_vector.tobytes()
