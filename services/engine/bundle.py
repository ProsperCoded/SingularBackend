from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .color_features import compare_color_signatures
from .phash import PHASH_THRESHOLD, SUPPORT_PHASH_THRESHOLD, compare_phash
from .pipeline import EnrolResult, FeatureResult, ImageSource, extract_features
from .vector import cosine_similarity


PASS_VECTOR_SIMILARITY = 0.975
SUSPICIOUS_VECTOR_SIMILARITY = 0.960
SUSPICIOUS_PRIMARY_PHASH_DISTANCE = 14
SUSPICIOUS_CANVAS_PHASH_DISTANCE = 18


@dataclass(frozen=True)
class VerificationSummary:
    product_id: str
    vendor_id: str | None
    verdict: str
    passed: bool
    vector_score: float
    mean_vector_score: float
    sample_vector_score: float
    structural_verdict: str
    color_verdict: str
    color_distance: float
    primary_phash_distance: int
    support_phash_distance: int
    canvas_phash_distance: int
    thresholds: dict[str, float | int | str]


def _vector_to_bundle(vector: np.ndarray) -> dict[str, object]:
    return {
        "dtype": str(vector.dtype),
        "shape": list(vector.shape),
        "data_b64": base64.b64encode(vector.tobytes()).decode("ascii"),
    }


def _vector_from_bundle(payload: Mapping[str, object]) -> np.ndarray:
    raw = base64.b64decode(str(payload["data_b64"]).encode("ascii"))
    array = np.frombuffer(raw, dtype=np.dtype(str(payload["dtype"])))
    return array.reshape(payload["shape"])


def serialize_enrolment_bundle(result: EnrolResult, vendor_id: str | None) -> dict[str, object]:
    return {
        "product_id": result.product_id,
        "vendor_id": vendor_id,
        "scan_count": result.scan_count,
        "primary_phash_str": result.primary_phash_str,
        "primary_phash_strs": list(result.primary_phash_strs),
        "support_phash_str": result.support_phash_str,
        "support_phash_strs": list(result.support_phash_strs),
        "canvas_phash_str": result.canvas_phash_str,
        "canvas_phash_strs": list(result.canvas_phash_strs),
        "combined_vector": _vector_to_bundle(result.combined_vector),
        "combined_vectors": [_vector_to_bundle(vector) for vector in result.combined_vectors],
        "color_signature": _vector_to_bundle(result.color_signature),
        "color_signatures": [_vector_to_bundle(signature) for signature in result.color_signatures],
    }


def load_enrolment_bundle(bundle_source: str | Path | Mapping[str, object]) -> dict[str, object]:
    if isinstance(bundle_source, Mapping):
        bundle: dict[str, object] = dict(bundle_source)
    else:
        bundle = json.loads(Path(bundle_source).read_text(encoding="utf-8"))

    bundle["combined_vector"] = _vector_from_bundle(bundle["combined_vector"])
    bundle["combined_vectors"] = tuple(
        _vector_from_bundle(payload) for payload in bundle.get("combined_vectors", [bundle["combined_vector"]])
    )
    bundle["color_signature"] = _vector_from_bundle(bundle["color_signature"])
    bundle["color_signatures"] = tuple(_vector_from_bundle(payload) for payload in bundle["color_signatures"])
    bundle.pop("lbp_sketch_b64", None)
    bundle.pop("lbp_sketch", None)
    bundle["primary_phash_strs"] = tuple(bundle.get("primary_phash_strs", [bundle["primary_phash_str"]]))
    bundle["support_phash_strs"] = tuple(bundle.get("support_phash_strs", [bundle["support_phash_str"]]))
    bundle["canvas_phash_strs"] = tuple(bundle.get("canvas_phash_strs", [bundle["canvas_phash_str"]]))
    return bundle


def _best_vector_score(bundle: Mapping[str, object], current_vector: np.ndarray) -> tuple[float, float]:
    mean_score = cosine_similarity(bundle["combined_vector"], current_vector)
    sample_score = max(cosine_similarity(vector, current_vector) for vector in bundle["combined_vectors"])
    return mean_score, sample_score


def _min_phash_distance(reference_hashes: Sequence[str], current_hash: str) -> int:
    return min(compare_phash(reference_hash, current_hash) for reference_hash in reference_hashes)


def _classify_structural_verdict(
    *,
    sample_vector_score: float,
    primary_distance: int,
    support_distance: int,
    canvas_distance: int,
) -> str:
    if sample_vector_score >= PASS_VECTOR_SIMILARITY and primary_distance <= PHASH_THRESHOLD:
        return "pass"
    if sample_vector_score >= SUSPICIOUS_VECTOR_SIMILARITY and (
        primary_distance <= SUSPICIOUS_PRIMARY_PHASH_DISTANCE
        or support_distance <= SUPPORT_PHASH_THRESHOLD
        or canvas_distance <= SUSPICIOUS_CANVAS_PHASH_DISTANCE
    ):
        return "suspicious"
    return "fail"


def _color_thresholds(bundle: Mapping[str, object]) -> tuple[float, float]:
    baseline = max(compare_color_signatures(signature, bundle["color_signature"]) for signature in bundle["color_signatures"])
    pass_threshold = min(max(0.15, baseline * 2.0), 0.35)
    suspicious_threshold = min(max(0.25, baseline * 3.0), 0.75)
    return pass_threshold, suspicious_threshold


def _classify_color_verdict(bundle: Mapping[str, object], current_signature: np.ndarray) -> tuple[str, float, float, float]:
    pass_threshold, suspicious_threshold = _color_thresholds(bundle)
    distance = compare_color_signatures(bundle["color_signature"], current_signature)
    if distance <= pass_threshold:
        return "pass", distance, pass_threshold, suspicious_threshold
    if distance <= suspicious_threshold:
        return "suspicious", distance, pass_threshold, suspicious_threshold
    return "fail", distance, pass_threshold, suspicious_threshold


def _merge_verdicts(
    *,
    structural_verdict: str,
    color_verdict: str,
    sample_vector_score: float,
    primary_distance: int,
) -> str:
    if structural_verdict == "fail":
        return "fail"
    if structural_verdict == "pass" and color_verdict == "fail":
        return "suspicious"
    if structural_verdict == "suspicious" and color_verdict == "pass":
        if sample_vector_score >= SUSPICIOUS_VECTOR_SIMILARITY and primary_distance <= SUSPICIOUS_PRIMARY_PHASH_DISTANCE:
            return "pass"
    if structural_verdict == "suspicious" and color_verdict == "fail":
        # Do not let color alone drag a structurally viable tag into a "FAKE" state.
        # It remains "suspicious".
        return "suspicious"
    return structural_verdict


def verify_enrolment_bundle(
    bundle_source: str | Path | Mapping[str, object],
    image_source: ImageSource,
) -> VerificationSummary:
    bundle = load_enrolment_bundle(bundle_source)
    current = extract_features(image_source)

    mean_vector_score, sample_vector_score = _best_vector_score(bundle, current.combined_vector)
    primary_distance = _min_phash_distance(bundle["primary_phash_strs"], current.primary_phash_str)
    support_distance = _min_phash_distance(bundle["support_phash_strs"], current.support_phash_str)
    canvas_distance = _min_phash_distance(bundle["canvas_phash_strs"], current.canvas_phash_str)

    structural_verdict = _classify_structural_verdict(
        sample_vector_score=sample_vector_score,
        primary_distance=primary_distance,
        support_distance=support_distance,
        canvas_distance=canvas_distance,
    )
    color_verdict, color_distance, color_pass_threshold, color_suspicious_threshold = _classify_color_verdict(
        bundle,
        current.color_signature,
    )
    verdict = _merge_verdicts(
        structural_verdict=structural_verdict,
        color_verdict=color_verdict,
        sample_vector_score=sample_vector_score,
        primary_distance=primary_distance,
    )

    return VerificationSummary(
        product_id=str(bundle["product_id"]),
        vendor_id=bundle.get("vendor_id") if bundle.get("vendor_id") is not None else None,
        verdict=verdict,
        passed=verdict == "pass",
        vector_score=sample_vector_score,
        mean_vector_score=mean_vector_score,
        sample_vector_score=sample_vector_score,
        structural_verdict=structural_verdict,
        color_verdict=color_verdict,
        color_distance=color_distance,
        primary_phash_distance=primary_distance,
        support_phash_distance=support_distance,
        canvas_phash_distance=canvas_distance,
        thresholds={
            "pass_vector_similarity": PASS_VECTOR_SIMILARITY,
            "suspicious_vector_similarity": SUSPICIOUS_VECTOR_SIMILARITY,
            "primary_phash_distance": PHASH_THRESHOLD,
            "suspicious_primary_phash_distance": SUSPICIOUS_PRIMARY_PHASH_DISTANCE,
            "suspicious_canvas_phash_distance": SUSPICIOUS_CANVAS_PHASH_DISTANCE,
            "support_phash_distance": SUPPORT_PHASH_THRESHOLD,
            "support_phash_distance_mode": "advisory",
            "color_distance_pass": color_pass_threshold,
            "color_distance_suspicious": color_suspicious_threshold,
        },
    )


def map_engine_verdict_to_backend(engine_verdict: str) -> str:
    mapping = {
        "pass": "AUTHENTIC",
        "suspicious": "SUSPICIOUS",
        "fail": "FAKE",
    }
    try:
        return mapping[engine_verdict]
    except KeyError as exc:
        raise ValueError(f"Unsupported engine verdict: {engine_verdict!r}") from exc
