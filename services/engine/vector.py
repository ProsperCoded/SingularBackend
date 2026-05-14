from __future__ import annotations

import numpy as np


def build_vector(
    lbp_vector: np.ndarray,
    sift_vector: np.ndarray,
    mobilenet_vector: np.ndarray,
) -> np.ndarray:
    if not isinstance(lbp_vector, np.ndarray):
        raise TypeError("lbp_vector must be a numpy array")
    if not isinstance(sift_vector, np.ndarray):
        raise TypeError("sift_vector must be a numpy array")
    if not isinstance(mobilenet_vector, np.ndarray):
        raise TypeError("mobilenet_vector must be a numpy array")
    if lbp_vector.ndim != 1 or sift_vector.ndim != 1 or mobilenet_vector.ndim != 1:
        raise ValueError("all input vectors must be 1D arrays")

    combined = np.concatenate([lbp_vector, sift_vector, mobilenet_vector]).astype(np.float32)
    norm = np.linalg.norm(combined) + 1e-12
    return (combined / norm).astype(np.float32)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    if not isinstance(vec_a, np.ndarray) or not isinstance(vec_b, np.ndarray):
        raise TypeError("vec_a and vec_b must be numpy arrays")
    if vec_a.ndim != 1 or vec_b.ndim != 1:
        raise ValueError("vec_a and vec_b must be 1D arrays")
    if vec_a.shape != vec_b.shape:
        raise ValueError("vec_a and vec_b must have the same shape")

    similarity = float(np.dot(vec_a, vec_b))
    return float(np.clip(similarity, 0.0, 1.0))
