from __future__ import annotations

import numpy as np
import pytest

from engine.calibration import CalibrationFeatures, compute_calibrated_score


def test_compute_calibrated_score_returns_none_without_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.calibration.load_score_calibrator", lambda: None)

    score = compute_calibrated_score(
        CalibrationFeatures(
            vector_similarity=0.9,
            lbp_similarity=0.85,
            primary_phash_distance=12,
            support_phash_distance=15,
            canvas_phash_distance=18,
            halftone_mean_score=10.0,
            halftone_max_score=12.0,
        )
    )

    assert score is None


def test_compute_calibrated_score_uses_predict_proba(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCalibrator:
        def predict_proba(self, features: np.ndarray) -> np.ndarray:
            assert features.shape == (1, 7)
            return np.asarray([[0.18, 0.82]], dtype=np.float32)

    monkeypatch.setattr("engine.calibration.load_score_calibrator", lambda: FakeCalibrator())

    score = compute_calibrated_score(
        CalibrationFeatures(
            vector_similarity=0.9,
            lbp_similarity=0.85,
            primary_phash_distance=12,
            support_phash_distance=15,
            canvas_phash_distance=18,
            halftone_mean_score=10.0,
            halftone_max_score=12.0,
        )
    )

    assert score == 82.0
