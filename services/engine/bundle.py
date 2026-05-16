from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .color_features import compare_color_signatures, infer_color_signature_version
from .halftone import HalftoneResult, is_photocopy
from .phash import compare_phash
from .pipeline import EnrolResult, ImageSource, extract_features
from .preprocessor import decode_qr_payload_bytes
from .vector import cosine_similarity


PASS_VECTOR_SIMILARITY = 0.975
SUSPICIOUS_VECTOR_SIMILARITY = 0.960
PASS_PRIMARY_PHASH_DISTANCE = 12
SUSPICIOUS_PRIMARY_PHASH_DISTANCE = 22
PASS_CANVAS_PHASH_DISTANCE = 16
SUSPICIOUS_CANVAS_PHASH_DISTANCE = 28
PASS_SUPPORT_PHASH_DISTANCE = 14
SUSPICIOUS_SUPPORT_PHASH_DISTANCE = 22
LBP_FAKE_THRESHOLD = 0.900
LBP_SUSPICIOUS_THRESHOLD = 0.940
LBP_SCORE_FLOOR = 0.850
PASS_LBP_SIMILARITY = 0.970
SHARPNESS_FAIL_RATIO = 0.600
SHARPNESS_SUSPICIOUS_RATIO = 0.780
PASS_SHARPNESS_RATIO = 0.920
AUTHENTIC_COMPOSITE_SCORE = 70.0
SUSPICIOUS_COMPOSITE_SCORE = 50.0

VECTOR_SCORE_WEIGHT = 0.00
PRIMARY_PHASH_WEIGHT = 0.15
LBP_SCORE_WEIGHT = 0.55
SHARPNESS_SCORE_WEIGHT = 0.20
CANVAS_PHASH_WEIGHT = 0.05
SUPPORT_PHASH_WEIGHT = 0.05

HALFTONE_SENSITIVITY = 2.5


@dataclass(frozen=True)
class VerificationSummary:
    product_id: str
    vendor_id: str | None
    verdict: str
    passed: bool
    lbp_score: float
    sharpness_score: float
    sharpness_ratio: float
    vector_score: float
    composite_score: float
    score_source: str
    mean_vector_score: float
    sample_vector_score: float
    enrolled_halftone_mean: float
    enrolled_halftone_max: float
    query_halftone_mean: float
    query_halftone_max: float
    structural_verdict: str
    color_verdict: str
    color_distance: float
    primary_phash_distance: int
    support_phash_distance: int
    canvas_phash_distance: int
    verdict_reasons: list[str]
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
        "color_signature_version": result.color_signature_version,
        "sharpness_score": result.sharpness_score,
        "sharpness_scores": list(result.sharpness_scores),
        "halftone_mean_score": result.halftone_mean_score,
        "halftone_max_score": result.halftone_max_score,
        "lbp_vector": _vector_to_bundle(result.lbp_vector),
        "lbp_vectors": [_vector_to_bundle(vector) for vector in result.lbp_vectors],
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
    if "lbp_vector" in bundle:
        bundle["lbp_vector"] = _vector_from_bundle(bundle["lbp_vector"])
        bundle["lbp_vectors"] = tuple(
            _vector_from_bundle(payload) for payload in bundle.get("lbp_vectors", [bundle["lbp_vector"]])
        )
    else:
        bundle["lbp_vector"] = None
        bundle["lbp_vectors"] = tuple()
    bundle["color_signature"] = _vector_from_bundle(bundle["color_signature"])
    bundle["color_signatures"] = tuple(_vector_from_bundle(payload) for payload in bundle["color_signatures"])
    explicit_color_version = bundle.get("color_signature_version")
    if explicit_color_version is not None:
        bundle["color_signature_version"] = str(explicit_color_version)
    else:
        bundle["color_signature_version"] = infer_color_signature_version(bundle["color_signature"])
    bundle.pop("lbp_sketch_b64", None)
    bundle.pop("lbp_sketch", None)
    bundle["sharpness_score"] = float(bundle.get("sharpness_score", 0.0))
    bundle["sharpness_scores"] = tuple(float(score) for score in bundle.get("sharpness_scores", [bundle["sharpness_score"]]))
    bundle["halftone_mean_score"] = float(bundle.get("halftone_mean_score", 0.0))
    bundle["halftone_max_score"] = float(bundle.get("halftone_max_score", 0.0))
    bundle["primary_phash_strs"] = tuple(bundle.get("primary_phash_strs", [bundle["primary_phash_str"]]))
    bundle["support_phash_strs"] = tuple(bundle.get("support_phash_strs", [bundle["support_phash_str"]]))
    bundle["canvas_phash_strs"] = tuple(bundle.get("canvas_phash_strs", [bundle["canvas_phash_str"]]))
    return bundle


def _current_vector_for_bundle(bundle: Mapping[str, object], current) -> np.ndarray:
    if bundle["combined_vector"].shape == current.combined_vector.shape:
        return current.combined_vector
    if bundle["combined_vector"].shape == current.legacy_combined_vector.shape:
        return current.legacy_combined_vector
    raise ValueError("combined vector shape is incompatible with current feature extractors")


def _current_lbp_for_bundle(bundle: Mapping[str, object], current) -> np.ndarray:
    if bundle["lbp_vectors"]:
        expected_shape = bundle["lbp_vectors"][0].shape
        if current.lbp_vector.shape == expected_shape:
            return current.lbp_vector
        if current.legacy_lbp_vector.shape == expected_shape:
            return current.legacy_lbp_vector
    if bundle["lbp_vector"] is not None:
        expected_shape = bundle["lbp_vector"].shape
        if current.lbp_vector.shape == expected_shape:
            return current.lbp_vector
        if current.legacy_lbp_vector.shape == expected_shape:
            return current.legacy_lbp_vector
    return current.lbp_vector


def _best_vector_score(bundle: Mapping[str, object], current) -> tuple[float, float]:
    current_vector = _current_vector_for_bundle(bundle, current)
    mean_score = cosine_similarity(bundle["combined_vector"], current_vector)
    sample_score = max(cosine_similarity(vector, current_vector) for vector in bundle["combined_vectors"])
    return mean_score, sample_score


def _best_lbp_score(bundle: Mapping[str, object], current) -> float:
    current_lbp = _current_lbp_for_bundle(bundle, current)
    if not bundle["lbp_vectors"]:
        return 1.0
    return max(cosine_similarity(vector, current_lbp) for vector in bundle["lbp_vectors"])


def _min_phash_distance(reference_hashes: Sequence[str], current_hash: str) -> int:
    return min(compare_phash(reference_hash, current_hash) for reference_hash in reference_hashes)


def _classify_structural_verdict(
    *,
    sample_vector_score: float,
    primary_distance: int,
    support_distance: int,
    canvas_distance: int,
) -> str:
    if (
        sample_vector_score >= PASS_VECTOR_SIMILARITY
        and primary_distance <= PASS_PRIMARY_PHASH_DISTANCE
        and support_distance <= PASS_SUPPORT_PHASH_DISTANCE
        and canvas_distance <= PASS_CANVAS_PHASH_DISTANCE
    ):
        return "pass"

    suspicious_signals = sum(
        (
            sample_vector_score >= SUSPICIOUS_VECTOR_SIMILARITY,
            primary_distance <= SUSPICIOUS_PRIMARY_PHASH_DISTANCE,
            support_distance <= SUSPICIOUS_SUPPORT_PHASH_DISTANCE,
            canvas_distance <= SUSPICIOUS_CANVAS_PHASH_DISTANCE,
        )
    )
    if suspicious_signals >= 2:
        return "suspicious"
    return "fail"


def _sharpness_ratio(enrolled_sharpness: float, current_sharpness: float) -> float:
    if enrolled_sharpness <= 0.0:
        return 1.0
    return float(np.clip(current_sharpness / enrolled_sharpness, 0.0, 2.0))


def _classify_texture_verdict(
    *,
    lbp_score: float,
    sharpness_ratio: float,
    halftone_detected: bool,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if halftone_detected:
        reasons.append("halftone_detected")
    if lbp_score < LBP_FAKE_THRESHOLD:
        reasons.append("lbp_texture_mismatch")
    if sharpness_ratio < SHARPNESS_FAIL_RATIO:
        reasons.append("sharpness_drop")
    if reasons:
        return "fail", reasons

    suspicious_reasons: list[str] = []
    if lbp_score < LBP_SUSPICIOUS_THRESHOLD:
        suspicious_reasons.append("lbp_texture_suspicious")
    if sharpness_ratio < SHARPNESS_SUSPICIOUS_RATIO:
        suspicious_reasons.append("sharpness_suspicious")
    if suspicious_reasons:
        return "suspicious", suspicious_reasons

    return "pass", []


def _compatible_color_signatures(
    bundle: Mapping[str, object],
    current_signature: np.ndarray,
) -> tuple[np.ndarray, ...]:
    compatible: list[np.ndarray] = []
    for signature in bundle["color_signatures"]:
        if signature.shape == current_signature.shape:
            compatible.append(signature)
    return tuple(compatible)


def _color_thresholds(bundle: Mapping[str, object]) -> tuple[float, float]:
    signatures = tuple(bundle["color_signatures"])
    distances: list[float] = []

    for index, left_signature in enumerate(signatures):
        for right_signature in signatures[index + 1 :]:
            distances.append(compare_color_signatures(left_signature, right_signature))

    if distances:
        baseline = max(distances)
    else:
        baseline = 0.0

    pass_threshold = min(max(0.22, baseline * 1.75), 0.35)
    suspicious_threshold = min(max(0.38, baseline * 2.75), 0.75)
    return pass_threshold, suspicious_threshold


def _classify_color_verdict(bundle: Mapping[str, object], current_signature: np.ndarray) -> tuple[str, float, float, float]:
    compatible_signatures = _compatible_color_signatures(bundle, current_signature)
    if not compatible_signatures:
        return "fail", float("inf"), float("inf"), float("inf")

    compatible_bundle = dict(bundle)
    compatible_bundle["color_signatures"] = compatible_signatures
    pass_threshold, suspicious_threshold = _color_thresholds(compatible_bundle)
    distance = min(
        compare_color_signatures(reference_signature, current_signature)
        for reference_signature in compatible_signatures
    )
    if distance <= pass_threshold:
        return "pass", distance, pass_threshold, suspicious_threshold
    if distance <= suspicious_threshold:
        return "suspicious", distance, pass_threshold, suspicious_threshold
    return "fail", distance, pass_threshold, suspicious_threshold


def _merge_verdicts(
    *,
    structural_verdict: str,
    texture_verdict: str,
    color_verdict: str,
) -> str:
    severity = {"pass": 0, "suspicious": 1, "fail": 2}
    merged = texture_verdict if severity[texture_verdict] >= severity[structural_verdict] else structural_verdict
    if merged == "pass" and color_verdict == "fail":
        return "suspicious"
    if merged == "suspicious" and color_verdict == "pass":
        return "pass"
    return merged


def _verdict_from_score(score: float) -> str:
    if score >= AUTHENTIC_COMPOSITE_SCORE:
        return "pass"
    if score >= SUSPICIOUS_COMPOSITE_SCORE:
        return "suspicious"
    return "fail"


def _normalize_similarity(score: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return float(np.clip((score - floor) / (ceiling - floor), 0.0, 1.0))


def _normalize_distance(distance: float, pass_threshold: float, suspicious_threshold: float) -> float:
    if distance <= pass_threshold:
        return 1.0
    if distance >= suspicious_threshold:
        return 0.0
    if suspicious_threshold <= pass_threshold:
        return 0.0
    return float(np.clip(1.0 - ((distance - pass_threshold) / (suspicious_threshold - pass_threshold)), 0.0, 1.0))


def _compute_composite_score(
    *,
    lbp_score: float,
    sharpness_ratio: float,
    sample_vector_score: float,
    primary_distance: int,
    support_distance: int,
    canvas_distance: int,
) -> float:
    lbp_component = _normalize_similarity(
        lbp_score,
        LBP_SCORE_FLOOR,
        PASS_LBP_SIMILARITY,
    )
    sharpness_component = _normalize_similarity(
        sharpness_ratio,
        SHARPNESS_FAIL_RATIO,
        PASS_SHARPNESS_RATIO,
    )
    primary_component = _normalize_distance(
        primary_distance,
        PASS_PRIMARY_PHASH_DISTANCE,
        SUSPICIOUS_PRIMARY_PHASH_DISTANCE,
    )
    support_component = _normalize_distance(
        support_distance,
        PASS_SUPPORT_PHASH_DISTANCE,
        SUSPICIOUS_SUPPORT_PHASH_DISTANCE,
    )
    canvas_component = _normalize_distance(
        canvas_distance,
        PASS_CANVAS_PHASH_DISTANCE,
        SUSPICIOUS_CANVAS_PHASH_DISTANCE,
    )
    weighted_total = (
        + (lbp_component * LBP_SCORE_WEIGHT)
        + (sharpness_component * SHARPNESS_SCORE_WEIGHT)
        + (primary_component * PRIMARY_PHASH_WEIGHT)
        + (canvas_component * CANVAS_PHASH_WEIGHT)
        + (support_component * SUPPORT_PHASH_WEIGHT)
    )
    return round(float(np.clip(weighted_total, 0.0, 1.0) * 100.0), 2)


def _align_score_with_verdict(score: float, verdict: str) -> float:
    if verdict == "fail":
        return round(min(score, SUSPICIOUS_COMPOSITE_SCORE - 0.01), 2)
    if verdict == "suspicious":
        return round(min(max(score, SUSPICIOUS_COMPOSITE_SCORE), AUTHENTIC_COMPOSITE_SCORE - 0.01), 2)
    return round(max(score, AUTHENTIC_COMPOSITE_SCORE), 2)


def verify_enrolment_bundle(
    bundle_source: str | Path | Mapping[str, object],
    image_source: ImageSource,
) -> VerificationSummary:
    bundle = load_enrolment_bundle(bundle_source)
    current = extract_features(
        image_source,
        color_signature_version=str(bundle["color_signature_version"]),
    )

    lbp_score = _best_lbp_score(bundle, current)
    sharpness_ratio = _sharpness_ratio(float(bundle["sharpness_score"]), current.sharpness_score)
    mean_vector_score, sample_vector_score = _best_vector_score(bundle, current)
    primary_distance = _min_phash_distance(bundle["primary_phash_strs"], current.primary_phash_str)
    support_distance = _min_phash_distance(bundle["support_phash_strs"], current.support_phash_str)
    canvas_distance = _min_phash_distance(bundle["canvas_phash_strs"], current.canvas_phash_str)
    color_verdict, color_distance, color_pass_threshold, color_suspicious_threshold = _classify_color_verdict(
        bundle,
        current.color_signature,
    )
    rule_based_score = _compute_composite_score(
        lbp_score=lbp_score,
        sharpness_ratio=sharpness_ratio,
        sample_vector_score=sample_vector_score,
        primary_distance=primary_distance,
        support_distance=support_distance,
        canvas_distance=canvas_distance,
    )
    enrolled_halftone = HalftoneResult(
        patch_scores=[],
        mean_score=float(bundle["halftone_mean_score"]),
        max_score=float(bundle["halftone_max_score"]),
    )
    query_halftone = HalftoneResult(
        patch_scores=[],
        mean_score=current.halftone_mean_score,
        max_score=current.halftone_max_score,
    )
    verdict_reasons: list[str] = []
    scanned_product_id: str | None = None
    try:
        _, scanned_product_id = decode_qr_payload_bytes(image_source)
    except Exception:
        scanned_product_id = None
    if scanned_product_id is not None and scanned_product_id != str(bundle["product_id"]):
        verdict_reasons.append("product_id_mismatch")

    halftone_detected = is_photocopy(
        query_halftone,
        enrolled_halftone,
        sensitivity=HALFTONE_SENSITIVITY,
    )
    texture_verdict, texture_reasons = _classify_texture_verdict(
        lbp_score=lbp_score,
        sharpness_ratio=sharpness_ratio,
        halftone_detected=halftone_detected,
    )
    verdict_reasons.extend(texture_reasons)
    structural_verdict = _classify_structural_verdict(
        sample_vector_score=sample_vector_score,
        primary_distance=primary_distance,
        support_distance=support_distance,
        canvas_distance=canvas_distance,
    )
    verdict = _merge_verdicts(
        structural_verdict=structural_verdict,
        texture_verdict=texture_verdict,
        color_verdict=color_verdict,
    )
    if "product_id_mismatch" in verdict_reasons:
        verdict = "fail"

    composite_score = _align_score_with_verdict(rule_based_score, verdict)
    score_source = "rule_based"

    return VerificationSummary(
        product_id=str(bundle["product_id"]),
        vendor_id=bundle.get("vendor_id") if bundle.get("vendor_id") is not None else None,
        verdict=verdict,
        passed=verdict == "pass",
        lbp_score=lbp_score,
        sharpness_score=current.sharpness_score,
        sharpness_ratio=sharpness_ratio,
        vector_score=sample_vector_score,
        composite_score=composite_score,
        score_source=score_source,
        mean_vector_score=mean_vector_score,
        sample_vector_score=sample_vector_score,
        enrolled_halftone_mean=float(bundle["halftone_mean_score"]),
        enrolled_halftone_max=float(bundle["halftone_max_score"]),
        query_halftone_mean=current.halftone_mean_score,
        query_halftone_max=current.halftone_max_score,
        structural_verdict=structural_verdict,
        color_verdict=color_verdict,
        color_distance=color_distance,
        primary_phash_distance=primary_distance,
        support_phash_distance=support_distance,
        canvas_phash_distance=canvas_distance,
        verdict_reasons=verdict_reasons,
        thresholds={
            "lbp_fake_threshold": LBP_FAKE_THRESHOLD,
            "lbp_suspicious_threshold": LBP_SUSPICIOUS_THRESHOLD,
            "lbp_score_floor": LBP_SCORE_FLOOR,
            "pass_lbp_similarity": PASS_LBP_SIMILARITY,
            "sharpness_fail_ratio": SHARPNESS_FAIL_RATIO,
            "sharpness_suspicious_ratio": SHARPNESS_SUSPICIOUS_RATIO,
            "pass_sharpness_ratio": PASS_SHARPNESS_RATIO,
            "pass_vector_similarity": PASS_VECTOR_SIMILARITY,
            "suspicious_vector_similarity": SUSPICIOUS_VECTOR_SIMILARITY,
            "authentic_composite_score": AUTHENTIC_COMPOSITE_SCORE,
            "suspicious_composite_score": SUSPICIOUS_COMPOSITE_SCORE,
            "score_source": score_source,
            "vector_score_weight": VECTOR_SCORE_WEIGHT,
            "primary_phash_weight": PRIMARY_PHASH_WEIGHT,
            "lbp_score_weight": LBP_SCORE_WEIGHT,
            "sharpness_score_weight": SHARPNESS_SCORE_WEIGHT,
            "canvas_phash_weight": CANVAS_PHASH_WEIGHT,
            "support_phash_weight": SUPPORT_PHASH_WEIGHT,
            "halftone_sensitivity": HALFTONE_SENSITIVITY,
            "primary_phash_distance": PASS_PRIMARY_PHASH_DISTANCE,
            "suspicious_primary_phash_distance": SUSPICIOUS_PRIMARY_PHASH_DISTANCE,
            "canvas_phash_distance": PASS_CANVAS_PHASH_DISTANCE,
            "suspicious_canvas_phash_distance": SUSPICIOUS_CANVAS_PHASH_DISTANCE,
            "support_phash_distance": PASS_SUPPORT_PHASH_DISTANCE,
            "suspicious_support_phash_distance": SUSPICIOUS_SUPPORT_PHASH_DISTANCE,
            "support_phash_distance_mode": "scored",
            "color_distance_mode": "advisory",
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
