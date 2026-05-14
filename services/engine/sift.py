from __future__ import annotations

import cv2
import numpy as np


def extract_sift(
    image_array: np.ndarray,
    n_features: int = 150,
    contrast_threshold: float = 0.03,
) -> np.ndarray:
    if not isinstance(image_array, np.ndarray):
        raise TypeError("image_array must be a numpy array")
    if image_array.ndim != 2:
        raise ValueError("image_array must be a 2D grayscale array")
    if n_features <= 0:
        raise ValueError("n_features must be a positive integer")
    if contrast_threshold <= 0:
        raise ValueError("contrast_threshold must be positive")

    sift = cv2.SIFT_create(
        nfeatures=n_features,
        contrastThreshold=contrast_threshold,
    )
    keypoints, descriptors = sift.detectAndCompute(image_array, None)

    if descriptors is None or keypoints is None or len(keypoints) < 5:
        return np.zeros(128, dtype=np.float32)

    return np.mean(descriptors, axis=0).astype(np.float32)
