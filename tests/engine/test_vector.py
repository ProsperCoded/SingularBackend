from __future__ import annotations

import numpy as np

from engine.generator import generate_qr
from engine.lbp import extract_lbp
from engine.mobilenet import extract_mobilenet
from engine.preprocessor import preprocess_tag
from engine.sift import extract_sift
from engine.vector import build_vector, cosine_similarity
from scripts.manual_artifacts import save_bytes


def test_build_vector_returns_expected_shape_and_dtype() -> None:
    lbp_vector = np.zeros(26, dtype=np.float32)
    sift_vector = np.zeros(128, dtype=np.float32)
    mobilenet_vector = np.zeros(1280, dtype=np.float32)

    combined = build_vector(lbp_vector, sift_vector, mobilenet_vector)

    assert combined.shape == (1434,)
    assert combined.dtype == np.float32


def test_build_vector_is_unit_normalized_for_nonzero_input() -> None:
    lbp_vector = np.ones(26, dtype=np.float32)
    sift_vector = np.ones(128, dtype=np.float32)
    mobilenet_vector = np.ones(1280, dtype=np.float32)

    combined = build_vector(lbp_vector, sift_vector, mobilenet_vector)

    assert np.isclose(float(np.linalg.norm(combined)), 1.0, atol=1e-6)


def test_cosine_similarity_of_identical_vector_is_one() -> None:
    vector = np.ones(1434, dtype=np.float32)
    normalized = build_vector(vector[:26], vector[26:154], vector[154:])

    assert np.isclose(cosine_similarity(normalized, normalized), 1.0, atol=1e-6)


def test_cosine_similarity_handles_zero_vectors() -> None:
    zero_vector = np.zeros(1434, dtype=np.float32)

    assert cosine_similarity(zero_vector, zero_vector) == 0.0


def test_build_vector_works_with_real_stage_outputs() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-123")
    primary_region = preprocess_tag(png_bytes).primary_region

    combined = build_vector(
        extract_lbp(primary_region),
        extract_sift(primary_region),
        extract_mobilenet(primary_region),
    )

    assert combined.shape == (1434,)
    assert np.isfinite(combined).all()


def test_vector_output_can_be_saved_for_manual_inspection() -> None:
    lbp_vector = np.ones(26, dtype=np.float32)
    sift_vector = np.ones(128, dtype=np.float32)
    mobilenet_vector = np.ones(1280, dtype=np.float32)
    combined = build_vector(lbp_vector, sift_vector, mobilenet_vector)

    output_path = save_bytes(combined.tobytes(), "vector-stage8-test.bin")

    assert output_path.exists()
    assert output_path.read_bytes() == combined.tobytes()
