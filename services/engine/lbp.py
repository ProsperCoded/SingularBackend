from __future__ import annotations

import numpy as np
from skimage.feature import local_binary_pattern


def extract_lbp(image_array: np.ndarray, P: int = 24, R: float = 3.0) -> np.ndarray:
    if not isinstance(image_array, np.ndarray):
        raise TypeError("image_array must be a numpy array")
    if image_array.ndim != 2:
        raise ValueError("image_array must be a 2D grayscale array")
    if P <= 0:
        raise ValueError("P must be a positive integer")
    if R <= 0:
        raise ValueError("R must be positive")

    lbp_image = local_binary_pattern(image_array, P, R, method="uniform")
    n_bins = P + 2
    histogram, _ = np.histogram(
        lbp_image.ravel(),
        bins=n_bins,
        range=(0, n_bins),
        density=True,
    )
    return histogram.astype(np.float32)


def compute_lbp_sketch(lbp_vector: np.ndarray) -> bytes:
    if not isinstance(lbp_vector, np.ndarray):
        raise TypeError("lbp_vector must be a numpy array")
    if lbp_vector.ndim != 1:
        raise ValueError("lbp_vector must be a 1D array")
    if lbp_vector.size < 16:
        raise ValueError("lbp_vector must have at least 16 bins")

    sorted_indices = np.argsort(-lbp_vector, kind="stable")[:16].astype(np.uint8)
    top_values = lbp_vector[sorted_indices]
    bins = np.linspace(0.0, max(float(top_values.max()), 1e-12), num=5, endpoint=True)
    quantized = np.digitize(top_values, bins[1:-1], right=False).astype(np.uint8)

    # 16 bytes of selected bin indices + 16 bytes of quantized levels = fixed 32-byte sketch.
    sketch = bytes(sorted_indices.tolist()) + bytes(quantized.tolist())
    return sketch
