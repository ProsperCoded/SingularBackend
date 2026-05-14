from __future__ import annotations

import cv2
import numpy as np

from .preprocessor import extract_reference_patches


PATCH_NAMES = ("red", "green", "blue")


def extract_color_signature(image_source: str | bytes | np.ndarray, patch_size: int = 64) -> np.ndarray:
    patches = extract_reference_patches(image_source, patch_size=patch_size)

    values: list[float] = []
    for name in PATCH_NAMES:
        patch = patches[name]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)

        saturation = hsv[:, :, 1].astype(np.float32)
        a_channel = lab[:, :, 1].astype(np.float32)
        b_channel = lab[:, :, 2].astype(np.float32)

        values.extend(
            [
                float(saturation.mean() / 255.0),
                float(saturation.std() / 255.0),
                float((a_channel.mean() - 128.0) / 127.0),
                float((b_channel.mean() - 128.0) / 127.0),
            ]
        )

    return np.asarray(values, dtype=np.float32)


def compare_color_signatures(signature_a: np.ndarray, signature_b: np.ndarray) -> float:
    if signature_a.shape != signature_b.shape:
        raise ValueError("color signatures must share the same shape")
    return float(np.linalg.norm(signature_a.astype(np.float32) - signature_b.astype(np.float32)))
