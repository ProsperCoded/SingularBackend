from __future__ import annotations

import cv2
import numpy as np

from engine.generator import generate_qr
from engine.halftone import HalftoneResult, is_photocopy, score_patch, score_patches
from engine.preprocessor import extract_reference_patches


def _patches_from_generated_tag() -> list[np.ndarray]:
    png_bytes = generate_qr(b"example-cbor-payload", "product-test-1")
    patches = extract_reference_patches(png_bytes, patch_size=64)
    return [cv2.cvtColor(patch, cv2.COLOR_BGR2RGB) for patch in patches.values()]


def _simulate_halftone(patch_rgb: np.ndarray, step: int = 8, radius: int = 2) -> np.ndarray:
    simulated = patch_rgb.copy().astype(np.uint8)
    output = simulated.copy()
    for y in range(step // 2, simulated.shape[0], step):
        for x in range(step // 2, simulated.shape[1], step):
            cv2.circle(output, (x, y), radius, (25, 25, 25), thickness=-1, lineType=cv2.LINE_AA)
    return output


def test_score_patch_returns_float() -> None:
    patch = _patches_from_generated_tag()[0]
    assert isinstance(score_patch(patch), float)


def test_score_patches_shape() -> None:
    patches = _patches_from_generated_tag()
    result = score_patches(patches)

    assert len(result.patch_scores) == len(patches)


def test_genuine_scores_lower_than_photocopy() -> None:
    enrolled_patches = _patches_from_generated_tag()
    reprint_patches = [_simulate_halftone(patch) for patch in enrolled_patches]

    enrolled_result = score_patches(enrolled_patches)
    reprint_result = score_patches(reprint_patches)

    assert enrolled_result.mean_score < reprint_result.mean_score


def test_is_photocopy_same_image_returns_false() -> None:
    patches = _patches_from_generated_tag()
    result = score_patches(patches)

    assert is_photocopy(result, result, sensitivity=2.5) is False


def test_score_patch_returns_zero_for_degenerate_inputs() -> None:
    assert score_patch(np.zeros((0, 0, 3), dtype=np.uint8)) == 0.0
    assert score_patch(np.zeros((8, 8), dtype=np.uint8)) == 0.0


def test_is_photocopy_fails_open_on_invalid_inputs() -> None:
    valid = HalftoneResult(patch_scores=[1.0], mean_score=1.0, max_score=1.0)

    assert is_photocopy(valid, None) is False  # type: ignore[arg-type]
