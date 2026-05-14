from __future__ import annotations

import numpy as np

from engine.pipeline import enrol, extract_features, generate_qr_only
from scripts.manual_artifacts import save_png_bytes


def test_generate_qr_only_returns_png_bytes() -> None:
    result = generate_qr_only("product-123", "vendor-abc")

    assert result.product_id == "product-123"
    assert isinstance(result.qr_png_bytes, bytes)
    assert result.qr_png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_extract_features_returns_expected_fields() -> None:
    qr_result = generate_qr_only("product-123", "vendor-abc")

    features = extract_features(qr_result.qr_png_bytes)

    assert features.combined_vector.shape == (1434,)
    assert features.combined_vector.dtype == np.float32
    assert features.color_signature.shape == (12,)
    assert features.color_signature.dtype == np.float32
    assert len(features.primary_phash_str) == 16
    assert len(features.support_phash_str) == 16
    assert len(features.canvas_phash_str) == 16


def test_enrol_returns_expected_fields_for_single_tag() -> None:
    qr_result = generate_qr_only("product-123", "vendor-abc")

    result = enrol(
        [qr_result.qr_png_bytes, qr_result.qr_png_bytes, qr_result.qr_png_bytes],
        "product-123",
        "vendor-abc",
    )

    assert result.product_id == "product-123"
    assert result.combined_vector.shape == (1434,)
    assert result.combined_vector.dtype == np.float32
    assert len(result.combined_vectors) == 3
    assert result.color_signature.shape == (12,)
    assert len(result.color_signatures) == 3
    assert len(result.primary_phash_str) == 16
    assert len(result.primary_phash_strs) == 3
    assert len(result.support_phash_str) == 16
    assert len(result.support_phash_strs) == 3
    assert len(result.canvas_phash_str) == 16
    assert len(result.canvas_phash_strs) == 3
    assert len(result.lbp_sketch) == 32
    assert result.updated_qr_png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.scan_count == 3


def test_pipeline_qr_output_can_be_saved_for_manual_inspection() -> None:
    result = generate_qr_only("product-123", "vendor-abc")

    output_path = save_png_bytes(result.qr_png_bytes, "pipeline-stage9-test.png")

    assert output_path.exists()
    assert output_path.read_bytes() == result.qr_png_bytes
