from __future__ import annotations

import cv2
import numpy as np
import pytest

from engine.generator import generate_qr
from engine.preprocessor import (
    LocalizationError,
    _generate_template_image,
    _refine_with_ecc,
    decode_qr_payload,
    extract_reference_patches,
    preprocess,
    preprocess_tag,
)
from engine.signer import sign_payload
from scripts.manual_artifacts import save_image_array


def test_preprocess_returns_expected_shape_and_dtype() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-test-1")

    result = preprocess(png_bytes)

    assert result.shape == (256, 256)
    assert result.dtype == np.uint8
    assert result.min() >= 0
    assert result.max() <= 255


def test_preprocess_bytes_input_matches_path_contract(tmp_path) -> None:
    image = cv2.imdecode(np.frombuffer(generate_qr(b"example-cbor-payload", "product-test-1"), dtype=np.uint8), cv2.IMREAD_COLOR)
    image_path = save_image_array(image, "sample.png", output_dir=tmp_path)

    path_result = preprocess(str(image_path))
    byte_result = preprocess(image_path.read_bytes())

    assert path_result.shape == (256, 256)
    assert byte_result.shape == (256, 256)


def test_preprocess_rejects_non_localizable_images() -> None:
    image = np.full((64, 64), 200, dtype=np.uint8)

    with pytest.raises(LocalizationError):
        preprocess(image, anchor_size=256, apply_clahe=False)


def test_preprocess_output_can_be_saved_for_manual_inspection() -> None:
    image = generate_qr(b"example-cbor-payload", "product-test-1")

    result = preprocess(image)
    output_path = save_image_array(result, "preprocessed-test.png")

    assert output_path.exists()
    saved = cv2.imread(str(output_path), cv2.IMREAD_GRAYSCALE)
    assert saved is not None
    assert saved.shape == (256, 256)


def test_preprocess_tag_returns_canvas_and_split_regions() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-test-1")

    tag = preprocess_tag(png_bytes)

    assert tag.canvas.ndim == 2
    assert tag.canvas.dtype == np.uint8
    assert tag.primary_region.shape == (256, 256)
    assert tag.support_region.shape == (256, 256)
    assert tag.primary_region.dtype == np.uint8
    assert tag.support_region.dtype == np.uint8


def test_preprocess_tag_retains_alignment_optimizations() -> None:
    signed_payload = sign_payload("product-test-1", "vendor-abc", b"\x00" * 32)
    png_bytes = generate_qr(signed_payload, "product-test-1")

    tag = preprocess_tag(png_bytes)

    assert tag.quality.aruco_marker_count >= 2
    assert "+aruco" in tag.alignment_method


def test_ecc_refinement_helper_runs_on_template_image() -> None:
    signed_payload = sign_payload("product-test-1", "vendor-abc", b"\x00" * 32)
    png_bytes = generate_qr(signed_payload, "product-test-1")

    source = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    payload_uri = decode_qr_payload(png_bytes)
    template_image = _generate_template_image(payload_uri)

    assert source is not None
    assert template_image is not None
    refined, correlation = _refine_with_ecc(source, template_image)
    assert refined.shape == source.shape
    assert correlation is not None


def test_decode_qr_payload_round_trips_generated_tag() -> None:
    signed_payload = sign_payload("product-test-1", "vendor-abc", b"\x00" * 32)
    png_bytes = generate_qr(signed_payload, "product-test-1")

    data = decode_qr_payload(png_bytes)

    assert data.startswith("printpuf://verify?data=")


def test_preprocess_tag_localizes_perspective_photo() -> None:
    source = cv2.imdecode(np.frombuffer(generate_qr(b"example-cbor-payload", "product-test-1"), dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = source.shape[:2]
    canvas = np.full((height * 3, width * 3, 3), 245, dtype=np.uint8)
    src_points = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    dst_points = np.array(
        [[80, 140], [width + 60, 120], [width + 110, height + 170], [95, height + 210]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(src_points, dst_points)
    warped = cv2.warpPerspective(source, transform, (canvas.shape[1], canvas.shape[0]), borderValue=(245, 245, 245))
    mask = cv2.warpPerspective(np.full((height, width), 255, dtype=np.uint8), transform, (canvas.shape[1], canvas.shape[0]))
    simulated_photo = canvas.copy()
    simulated_photo[mask > 0] = warped[mask > 0]

    tag = preprocess_tag(simulated_photo)

    assert tag.primary_region.shape == (256, 256)
    assert tag.support_region.shape == (256, 256)
    assert tag.canvas.shape[0] > 0


def test_extract_reference_patches_returns_rgb_anchors() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-test-1")

    patches = extract_reference_patches(png_bytes, patch_size=48)

    assert set(patches) == {"red", "green", "blue"}
    assert patches["red"].shape == (48, 48, 3)
    assert patches["green"].shape == (48, 48, 3)
    assert patches["blue"].shape == (48, 48, 3)

    red_mean = patches["red"].mean(axis=(0, 1))
    green_mean = patches["green"].mean(axis=(0, 1))
    blue_mean = patches["blue"].mean(axis=(0, 1))

    assert red_mean[2] > red_mean[1]
    assert red_mean[2] > red_mean[0]
    assert green_mean[1] > green_mean[2]
    assert green_mean[1] > green_mean[0]
    assert blue_mean[0] > blue_mean[1]
    assert blue_mean[0] > blue_mean[2]
