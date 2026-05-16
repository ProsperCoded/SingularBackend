from __future__ import annotations

import numpy as np
from skimage.feature import local_binary_pattern


def extract_lbp(
    image_array: np.ndarray,
    P: int = 8,
    R: float = 1.0,
    method: str = "default",
) -> np.ndarray:
    if not isinstance(image_array, np.ndarray):
        raise TypeError("image_array must be a numpy array")
    if image_array.ndim != 2:
        raise ValueError("image_array must be a 2D grayscale array")
    if P <= 0:
        raise ValueError("P must be a positive integer")
    if R <= 0:
        raise ValueError("R must be positive")

    lbp_image = local_binary_pattern(image_array, P, R, method=method)
    if method == "default" and P == 8:
        n_bins = 256
    else:
        n_bins = int(lbp_image.max() + 1)
    histogram, _ = np.histogram(
        lbp_image.ravel(),
        bins=n_bins,
        range=(0, n_bins),
        density=True,
    )
    return histogram.astype(np.float32)
