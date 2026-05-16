from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from core.config import settings

try:  # pragma: no cover - optional dependency
    import joblib
except Exception:  # pragma: no cover - optional dependency
    joblib = None


@runtime_checkable
class ProbabilityCalibrator(Protocol):
    def predict_proba(self, features: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class CalibrationFeatures:
    vector_similarity: float
    lbp_similarity: float
    primary_phash_distance: int
    support_phash_distance: int
    canvas_phash_distance: int
    halftone_mean_score: float
    halftone_max_score: float

    def to_model_input(self) -> np.ndarray:
        return np.asarray(
            [
                [
                    self.vector_similarity,
                    self.lbp_similarity,
                    float(self.primary_phash_distance),
                    float(self.support_phash_distance),
                    float(self.canvas_phash_distance),
                    self.halftone_mean_score,
                    self.halftone_max_score,
                ]
            ],
            dtype=np.float32,
        )


@lru_cache(maxsize=1)
def load_score_calibrator() -> ProbabilityCalibrator | None:
    calibrator_path = settings.PRINTPUF_SCORE_CALIBRATOR_PATH
    if not calibrator_path:
        return None

    path = Path(calibrator_path)
    if not path.exists() or joblib is None:
        return None

    try:
        loaded = joblib.load(path)
    except Exception:
        return None

    if not isinstance(loaded, ProbabilityCalibrator):
        return None
    return loaded


def compute_calibrated_score(features: CalibrationFeatures) -> float | None:
    calibrator = load_score_calibrator()
    if calibrator is None:
        return None

    try:
        probabilities = calibrator.predict_proba(features.to_model_input())
        genuine_probability = float(probabilities[0][1])
    except Exception:
        return None

    return round(float(np.clip(genuine_probability, 0.0, 1.0) * 100.0), 2)
