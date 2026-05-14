from __future__ import annotations

import cv2
import numpy as np

from engine.generator import generate_qr
from scripts.manual_artifacts import save_png_bytes


def test_generate_qr_returns_png_bytes() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-123")

    assert isinstance(png_bytes, bytes)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 0


def test_generate_qr_png_is_decodable_image() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-123")

    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert image is not None
    assert image.ndim == 3
    assert image.shape[0] > 0
    assert image.shape[1] > 0
    assert np.any(image[:, :, 0] != image[:, :, 1]) or np.any(image[:, :, 1] != image[:, :, 2])

    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(image)

    assert data.startswith("printpuf://verify?data=")


def test_generate_qr_output_can_be_saved_for_manual_inspection() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-123")
    output_path = save_png_bytes(png_bytes, "qr-stage1-test.png")

    assert output_path.exists()
    saved = cv2.imread(str(output_path), cv2.IMREAD_GRAYSCALE)
    assert saved is not None
    assert saved.shape[0] > 0
    assert saved.shape[1] > 0
