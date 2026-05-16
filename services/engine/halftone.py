from __future__ import annotations

from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

try:
    from skimage.feature import graycomatrix, graycoprops
except Exception:  # pragma: no cover - optional dependency fallback
    graycomatrix = None
    graycoprops = None


@dataclass(frozen=True)
class HalftoneResult:
    patch_scores: List[float]
    mean_score: float
    max_score: float


def _to_grayscale_patch(patch_rgb: np.ndarray) -> np.ndarray | None:
    if not isinstance(patch_rgb, np.ndarray):
        return None
    if patch_rgb.size == 0:
        return None

    if patch_rgb.ndim == 2:
        gray = patch_rgb
    elif patch_rgb.ndim == 3 and patch_rgb.shape[2] == 3:
        gray = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2GRAY)
    else:
        return None

    if gray.shape[0] < 16 or gray.shape[1] < 16:
        return None
    if gray.dtype != np.uint8:
        gray = np.clip(gray, 0, 255).astype(np.uint8)
    return gray


def _fft_periodicity_score(gray_patch: np.ndarray) -> float:
    resized = cv2.resize(gray_patch, (128, 128), interpolation=cv2.INTER_AREA)
    spectrum = np.fft.fftshift(np.fft.fft2(resized.astype(np.float32)))
    magnitude = np.abs(spectrum)
    magnitude[60:68, 60:68] = 0.0
    top_peak = float(np.partition(magnitude.ravel(), -20)[-20:].mean())
    total_mean = float(magnitude.mean()) + 1e-12
    return float(top_peak / total_mean)


def _glcm_regularization_score(gray_patch: np.ndarray) -> float:
    if graycomatrix is None or graycoprops is None:
        return 0.0

    resized = cv2.resize(gray_patch, (128, 128), interpolation=cv2.INTER_AREA)
    quantized = (resized // 8).astype(np.uint8)
    glcm = graycomatrix(
        quantized,
        distances=[1, 2],
        angles=[0.0, np.pi / 4.0, np.pi / 2.0, 3.0 * np.pi / 4.0],
        levels=32,
        symmetric=True,
        normed=True,
    )
    homogeneity = float(graycoprops(glcm, "homogeneity").mean())
    return homogeneity * 30.0


def score_patch(patch_rgb: np.ndarray) -> float:
    """
    Compute FFT periodicity score for a single color patch.
    High score = periodic halftone pattern (photocopy indicator).
    Low score = irregular ink scatter (genuine print).

    Args:
        patch_rgb: RGB uint8 numpy array of any size (will be resized internally)
    Returns:
        float >= 0. Genuine prints typically < 15.0. Photocopies typically > 35.0.
        These are relative baselines — use enrolled_mean * multiplier for gating.
    """

    gray = _to_grayscale_patch(patch_rgb)
    if gray is None:
        return 0.0

    fft_score = _fft_periodicity_score(gray)
    glcm_score = _glcm_regularization_score(gray)
    if glcm_score <= 0.0:
        return float(fft_score)
    return float((fft_score * 0.7) + (glcm_score * 0.3))


def score_patches(patches: List[np.ndarray]) -> HalftoneResult:
    """
    Score a list of color patch crops and return aggregated result.
    Patches are the output of extract_reference_patches().
    """

    patch_scores = [float(score_patch(patch)) for patch in patches]
    if not patch_scores:
        return HalftoneResult(patch_scores=[], mean_score=0.0, max_score=0.0)
    return HalftoneResult(
        patch_scores=patch_scores,
        mean_score=float(np.mean(patch_scores)),
        max_score=float(np.max(patch_scores)),
    )


def is_photocopy(
    query_result: HalftoneResult,
    enrolled_result: HalftoneResult,
    sensitivity: float = 2.5,
) -> bool:
    """
    Gate function. Returns True if the query scan shows significantly more
    periodic dot structure than the enrolled original.
    sensitivity=2.5 means query must be 2.5x more periodic than enrolled
    to trigger. Increase to 3.0 to reduce false positives on worn prints.
    """

    try:
        if sensitivity <= 0.0:
            return False

        if float(enrolled_result.mean_score) <= 0.0 and float(enrolled_result.max_score) <= 0.0:
            return False

        enrolled_mean = max(float(enrolled_result.mean_score), 1e-6)
        enrolled_max = max(float(enrolled_result.max_score), 1e-6)
        query_mean = float(query_result.mean_score)
        query_max = float(query_result.max_score)

        return (query_mean >= (enrolled_mean * sensitivity)) or (query_max >= (enrolled_max * sensitivity))
    except Exception:
        return False
