"""PrintPUF engine package."""

from .color_features import compare_color_signatures, extract_color_signature
from .generator import generate_qr
from .lbp import compute_lbp_sketch, extract_lbp
from .phash import (
    PHASH_THRESHOLD,
    SUPPORT_PHASH_THRESHOLD,
    RegionPHash,
    compare_phash,
    compute_phash,
    compute_region_phashes,
)
from .pipeline import EnrolResult, FeatureResult, GenerateResult, enrol, extract_features, generate_qr_only
from .preprocessor import (
    ImageQualityError,
    LocalizationError,
    PreprocessedTag,
    TagQuality,
    decode_qr_payload,
    decode_qr_payload_bytes,
    extract_reference_patches,
    preprocess,
    preprocess_tag,
)
from .sift import extract_sift
from .signer import sign_payload, verify_payload
from .vector import build_vector, cosine_similarity

__all__ = [
    "EnrolResult",
    "FeatureResult",
    "GenerateResult",
    "ImageQualityError",
    "LocalizationError",
    "PHASH_THRESHOLD",
    "PreprocessedTag",
    "RegionPHash",
    "SUPPORT_PHASH_THRESHOLD",
    "TagQuality",
    "build_vector",
    "compare_color_signatures",
    "compare_phash",
    "compute_lbp_sketch",
    "compute_phash",
    "compute_region_phashes",
    "cosine_similarity",
    "decode_qr_payload",
    "decode_qr_payload_bytes",
    "enrol",
    "extract_features",
    "extract_color_signature",
    "extract_lbp",
    "extract_reference_patches",
    "extract_sift",
    "generate_qr",
    "generate_qr_only",
    "preprocess",
    "preprocess_tag",
    "sign_payload",
    "verify_payload",
]
