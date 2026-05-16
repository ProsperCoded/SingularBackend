from __future__ import annotations

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import cbor2
import cv2
import numpy as np

from .color_features import COLOR_SIGNATURE_VERSION_CURRENT, extract_color_signature
from .generator import generate_qr
from .halftone import score_patches
from .lbp import extract_lbp
from .mobilenet import extract_mobilenet
from .phash import compute_region_phashes
from .preprocessor import PreprocessedTag, compute_sharpness_score, preprocess_tag
from .preprocessor import extract_reference_patches
from .sift import extract_sift
from .signer import sign_payload
from .vector import build_vector


DEFAULT_ENROLMENT_SCAN_COUNT = 3


ImageSource = str | bytes | np.ndarray


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector) + 1e-12
    return (vector.astype(np.float32) / norm).astype(np.float32)


def _extract_halftone_scores(image_source: ImageSource) -> tuple[float, float]:
    try:
        halftone_result = score_patches(
            [
                cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)
                for patch in extract_reference_patches(image_source).values()
            ]
        )
        return halftone_result.mean_score, halftone_result.max_score
    except Exception:
        return 0.0, 0.0


@dataclass(frozen=True)
class GenerateResult:
    product_id: str
    qr_png_bytes: bytes


@dataclass(frozen=True)
class EnrolResult:
    product_id: str
    lbp_vector: np.ndarray
    lbp_vectors: tuple[np.ndarray, ...]
    sharpness_score: float
    sharpness_scores: tuple[float, ...]
    combined_vector: np.ndarray
    combined_vectors: tuple[np.ndarray, ...]
    halftone_mean_score: float
    halftone_max_score: float
    color_signature_version: str
    color_signature: np.ndarray
    color_signatures: tuple[np.ndarray, ...]
    primary_phash_str: str
    primary_phash_strs: tuple[str, ...]
    support_phash_str: str
    support_phash_strs: tuple[str, ...]
    canvas_phash_str: str
    canvas_phash_strs: tuple[str, ...]
    updated_qr_png_bytes: bytes
    scan_count: int


@dataclass(frozen=True)
class FeatureResult:
    lbp_vector: np.ndarray
    legacy_lbp_vector: np.ndarray
    sharpness_score: float
    combined_vector: np.ndarray
    legacy_combined_vector: np.ndarray
    halftone_mean_score: float
    halftone_max_score: float
    color_signature: np.ndarray
    primary_phash_str: str
    support_phash_str: str
    canvas_phash_str: str


def _decode_product_id_from_payload_uri(payload_uri: str) -> str:
    parsed = urlparse(payload_uri)
    if parsed.scheme != "printpuf":
        raise ValueError("decoded QR does not use the printpuf scheme")

    encoded_payload = parse_qs(parsed.query).get("data", [None])[0]
    if not encoded_payload:
        raise ValueError("decoded QR payload is missing the data parameter")

    cbor_bytes = base64.urlsafe_b64decode(encoded_payload.encode("ascii"))
    payload = cbor2.loads(cbor_bytes)
    product_id = payload["pid"]
    if not isinstance(product_id, str) or not product_id:
        raise ValueError("decoded QR payload is missing a valid product id")
    return product_id


def _normalize_scan_sources(image_source: ImageSource | Sequence[ImageSource]) -> tuple[ImageSource, ...]:
    if isinstance(image_source, (str, bytes, np.ndarray)):
        return (image_source,)

    scans = tuple(image_source)
    if not scans:
        raise ValueError("image_source sequence must contain at least one image")
    return scans


def _validate_product_id(tag: PreprocessedTag, product_id: str) -> None:
    if tag.payload_uri is None:
        raise ValueError("enrolment image must contain a decodable QR payload")

    decoded_product_id = _decode_product_id_from_payload_uri(tag.payload_uri)
    if decoded_product_id != product_id:
        raise ValueError(f"enrolment image payload product_id {decoded_product_id!r} does not match {product_id!r}")


def generate_qr_only(
    product_id: str,
    vendor_id: str | None,
    private_key_pem: bytes | None = None,
) -> GenerateResult:
    cbor_payload = sign_payload(product_id, vendor_id, private_key_pem=private_key_pem)
    qr_png_bytes = generate_qr(cbor_payload, product_id)
    return GenerateResult(product_id=product_id, qr_png_bytes=qr_png_bytes)


def enrol(
    image_source: ImageSource | Sequence[ImageSource],
    product_id: str,
    vendor_id: str | None,
    private_key_pem: bytes | None = None,
    required_scan_count: int = DEFAULT_ENROLMENT_SCAN_COUNT,
) -> EnrolResult:
    if required_scan_count <= 0:
        raise ValueError("required_scan_count must be a positive integer")

    scan_sources = _normalize_scan_sources(image_source)
    if len(scan_sources) < required_scan_count:
        raise ValueError(f"expected at least {required_scan_count} enrolment images, got {len(scan_sources)}")

    preprocessed_tags = tuple(preprocess_tag(source) for source in scan_sources)
    for tag in preprocessed_tags:
        _validate_product_id(tag, product_id)

    region_hashes = tuple(compute_region_phashes(tag) for tag in preprocessed_tags)
    halftone_scores = tuple(_extract_halftone_scores(source) for source in scan_sources)
    color_signatures = tuple(
        extract_color_signature(source, descriptor_version=COLOR_SIGNATURE_VERSION_CURRENT)
        for source in scan_sources
    )
    lbp_vectors = tuple(_normalize_vector(extract_lbp(tag.texture_region)) for tag in preprocessed_tags)
    sharpness_scores = tuple(compute_sharpness_score(tag.texture_region) for tag in preprocessed_tags)
    sift_vectors = tuple(extract_sift(tag.primary_region) for tag in preprocessed_tags)
    mobilenet_vectors = tuple(extract_mobilenet(tag.primary_region) for tag in preprocessed_tags)
    combined_vectors = tuple(
        build_vector(lbp_vector, sift_vector, mobilenet_vector)
        for lbp_vector, sift_vector, mobilenet_vector in zip(lbp_vectors, sift_vectors, mobilenet_vectors, strict=True)
    )

    lbp_vector = _normalize_vector(np.mean(np.stack(lbp_vectors, axis=0), axis=0).astype(np.float32))
    sharpness_score = float(np.mean(sharpness_scores))
    combined_vector = np.mean(np.stack(combined_vectors, axis=0), axis=0).astype(np.float32)
    combined_norm = np.linalg.norm(combined_vector) + 1e-12
    combined_vector = (combined_vector / combined_norm).astype(np.float32)
    halftone_mean_score = float(np.mean([score[0] for score in halftone_scores]))
    halftone_max_score = float(np.max([score[1] for score in halftone_scores]))
    color_signature = np.mean(np.stack(color_signatures, axis=0), axis=0).astype(np.float32)

    cbor_payload = sign_payload(product_id, vendor_id, private_key_pem=private_key_pem)
    updated_qr_png_bytes = generate_qr(cbor_payload, product_id)

    primary_phash_strs = tuple(item.primary_hash for item in region_hashes)
    support_phash_strs = tuple(item.support_hash for item in region_hashes)
    canvas_phash_strs = tuple(item.canvas_hash for item in region_hashes)

    return EnrolResult(
        product_id=product_id,
        lbp_vector=lbp_vector,
        lbp_vectors=lbp_vectors,
        sharpness_score=sharpness_score,
        sharpness_scores=sharpness_scores,
        combined_vector=combined_vector,
        combined_vectors=combined_vectors,
        halftone_mean_score=halftone_mean_score,
        halftone_max_score=halftone_max_score,
        color_signature_version=COLOR_SIGNATURE_VERSION_CURRENT,
        color_signature=color_signature,
        color_signatures=color_signatures,
        primary_phash_str=primary_phash_strs[0],
        primary_phash_strs=primary_phash_strs,
        support_phash_str=support_phash_strs[0],
        support_phash_strs=support_phash_strs,
        canvas_phash_str=canvas_phash_strs[0],
        canvas_phash_strs=canvas_phash_strs,
        updated_qr_png_bytes=updated_qr_png_bytes,
        scan_count=len(preprocessed_tags),
    )


def extract_features(
    image_source: ImageSource,
    color_signature_version: str = COLOR_SIGNATURE_VERSION_CURRENT,
) -> FeatureResult:
    preprocessed_tag = preprocess_tag(image_source)
    region_hashes = compute_region_phashes(preprocessed_tag)
    lbp_vector = _normalize_vector(extract_lbp(preprocessed_tag.texture_region))
    legacy_lbp_vector = _normalize_vector(
        extract_lbp(preprocessed_tag.texture_region, P=24, R=3.0, method="uniform")
    )
    sharpness_score = compute_sharpness_score(preprocessed_tag.texture_region)
    halftone_mean_score, halftone_max_score = _extract_halftone_scores(image_source)
    sift_vector = extract_sift(preprocessed_tag.primary_region)
    mobilenet_vector = extract_mobilenet(preprocessed_tag.primary_region)
    combined_vector = build_vector(
        lbp_vector,
        sift_vector,
        mobilenet_vector,
    )
    legacy_combined_vector = build_vector(
        legacy_lbp_vector,
        sift_vector,
        mobilenet_vector,
    )
    color_signature = extract_color_signature(
        image_source,
        descriptor_version=color_signature_version,
    )

    return FeatureResult(
        lbp_vector=lbp_vector,
        legacy_lbp_vector=legacy_lbp_vector,
        sharpness_score=sharpness_score,
        combined_vector=combined_vector,
        legacy_combined_vector=legacy_combined_vector,
        halftone_mean_score=halftone_mean_score,
        halftone_max_score=halftone_max_score,
        color_signature=color_signature,
        primary_phash_str=region_hashes.primary_hash,
        support_phash_str=region_hashes.support_hash,
        canvas_phash_str=region_hashes.canvas_hash,
    )
