from __future__ import annotations

import numpy as np

from engine.bundle import (
    AUTHENTIC_COMPOSITE_SCORE,
    SUSPICIOUS_COMPOSITE_SCORE,
    _compute_composite_score,
    _verdict_from_score,
)


def test_composite_score_drives_authentic_verdict_for_strong_match() -> None:
    score = _compute_composite_score(
        lbp_score=0.95,
        sample_vector_score=0.92,
        primary_distance=12,
        support_distance=14,
        canvas_distance=16,
    )

    assert score >= AUTHENTIC_COMPOSITE_SCORE
    assert _verdict_from_score(score) == "pass"


def test_low_vector_similarity_keeps_verdict_fake_even_when_distances_pass() -> None:
    score = _compute_composite_score(
        lbp_score=0.95,
        sample_vector_score=0.60,
        primary_distance=12,
        support_distance=14,
        canvas_distance=16,
    )

    assert score < SUSPICIOUS_COMPOSITE_SCORE
    assert _verdict_from_score(score) == "fail"


def test_weighted_score_matches_expected_breakdown() -> None:
    score = _compute_composite_score(
        lbp_score=0.88,
        sample_vector_score=0.86,
        primary_distance=14,
        support_distance=16,
        canvas_distance=18,
    )

    assert np.isclose(score, 72.9)
