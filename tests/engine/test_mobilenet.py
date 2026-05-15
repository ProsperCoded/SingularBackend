from __future__ import annotations

import numpy as np

from engine.generator import generate_qr
from engine.mobilenet import extract_mobilenet, get_model
from engine.preprocessor import preprocess_tag
from scripts.manual_artifacts import save_bytes


def test_extract_mobilenet_returns_expected_shape_and_dtype() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)

    embedding = extract_mobilenet(image)

    assert embedding.shape == (1280,)
    assert embedding.dtype == np.float32


def test_mobilenet_model_is_singleton() -> None:
    assert id(get_model()) == id(get_model())


def test_extract_mobilenet_returns_finite_embedding_for_generated_primary_region() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-test-1")
    primary_region = preprocess_tag(png_bytes).primary_region

    embedding = extract_mobilenet(primary_region)

    assert embedding.shape == (1280,)
    assert np.isfinite(embedding).all()


def test_mobilenet_output_can_be_saved_for_manual_inspection() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)
    embedding = extract_mobilenet(image)

    output_path = save_bytes(embedding.tobytes(), "mobilenet-stage7-test.bin")

    assert output_path.exists()
    assert output_path.read_bytes() == embedding.tobytes()
