from __future__ import annotations

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import cbor2
import numpy as np

from .color_features import extract_color_signature
from .generator import generate_qr
from .lbp import extract_lbp
from .mobilenet import extract_mobilenet
from .phash import compute_region_phashes
from .preprocessor import PreprocessedTag, preprocess_tag
from .sift import extract_sift
from .signer import sign_payload
from .vector import build_vector


DEFAULT_ENROLMENT_SCAN_COUNT = 3


ImageSource = str | bytes | np.ndarray


@dataclass(frozen=True)
class GenerateResult:
    product_id: str
    qr_png_bytes: bytes


@dataclass(frozen=True)
class EnrolResult:
    product_id: str
    combined_vector: np.ndarray
    combined_vectors: tuple[np.ndarray, ...]
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
    combined_vector: np.ndarray
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
    color_signatures = tuple(extract_color_signature(source) for source in scan_sources)
    lbp_vectors = tuple(extract_lbp(tag.primary_region) for tag in preprocessed_tags)
    sift_vectors = tuple(extract_sift(tag.primary_region) for tag in preprocessed_tags)
    mobilenet_vectors = tuple(extract_mobilenet(tag.primary_region) for tag in preprocessed_tags)
    combined_vectors = tuple(
        build_vector(lbp_vector, sift_vector, mobilenet_vector)
        for lbp_vector, sift_vector, mobilenet_vector in zip(lbp_vectors, sift_vectors, mobilenet_vectors, strict=True)
    )

    combined_vector = np.mean(np.stack(combined_vectors, axis=0), axis=0).astype(np.float32)
    combined_norm = np.linalg.norm(combined_vector) + 1e-12
    combined_vector = (combined_vector / combined_norm).astype(np.float32)
    color_signature = np.mean(np.stack(color_signatures, axis=0), axis=0).astype(np.float32)

    cbor_payload = sign_payload(product_id, vendor_id, private_key_pem=private_key_pem)
    updated_qr_png_bytes = generate_qr(cbor_payload, product_id)

    primary_phash_strs = tuple(item.primary_hash for item in region_hashes)
    support_phash_strs = tuple(item.support_hash for item in region_hashes)
    canvas_phash_strs = tuple(item.canvas_hash for item in region_hashes)

    return EnrolResult(
        product_id=product_id,
        combined_vector=combined_vector,
        combined_vectors=combined_vectors,
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


def extract_features(image_source: ImageSource) -> FeatureResult:
    preprocessed_tag = preprocess_tag(image_source)
    region_hashes = compute_region_phashes(preprocessed_tag)
    combined_vector = build_vector(
        extract_lbp(preprocessed_tag.primary_region),
        extract_sift(preprocessed_tag.primary_region),
        extract_mobilenet(preprocessed_tag.primary_region),
    )
    color_signature = extract_color_signature(image_source)

    return FeatureResult(
        combined_vector=combined_vector,
        color_signature=color_signature,
        primary_phash_str=region_hashes.primary_hash,
        support_phash_str=region_hashes.support_hash,
        canvas_phash_str=region_hashes.canvas_hash,
    )
