from __future__ import annotations

import numpy as np

from engine.generator import generate_qr
from engine.preprocessor import preprocess_tag
from engine.sift import extract_sift
from scripts.manual_artifacts import save_bytes


def test_extract_sift_returns_expected_shape_and_dtype() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)

    sift_vector = extract_sift(image)

    assert sift_vector.shape == (128,)
    assert sift_vector.dtype == np.float32


def test_extract_sift_returns_zero_vector_for_blank_image() -> None:
    image = np.full((256, 256), 255, dtype=np.uint8)

    sift_vector = extract_sift(image)

    assert np.array_equal(sift_vector, np.zeros(128, dtype=np.float32))


def test_extract_sift_returns_nonzero_vector_for_generated_primary_region() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-123")
    primary_region = preprocess_tag(png_bytes).primary_region

    sift_vector = extract_sift(primary_region)

    assert sift_vector.shape == (128,)
    assert np.any(sift_vector != 0.0)


def test_sift_output_can_be_saved_for_manual_inspection() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)
    sift_vector = extract_sift(image)

    output_path = save_bytes(sift_vector.tobytes(), "sift-stage6-test.bin")

    assert output_path.exists()
    assert output_path.read_bytes() == sift_vector.tobytes()
