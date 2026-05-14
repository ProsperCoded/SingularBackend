from __future__ import annotations

from dataclasses import dataclass

import imagehash
import numpy as np
from PIL import Image

from .preprocessor import PreprocessedTag


PHASH_THRESHOLD = 10
SUPPORT_PHASH_THRESHOLD = 16


@dataclass(frozen=True)
class RegionPHash:
    canvas_hash: str
    primary_hash: str
    support_hash: str


def compute_phash(image_array: np.ndarray) -> str:
    if not isinstance(image_array, np.ndarray):
        raise TypeError("image_array must be a numpy array")
    if image_array.ndim != 2:
        raise ValueError("image_array must be a 2D grayscale array")

    pil_image = Image.fromarray(image_array.astype(np.uint8), mode="L")
    return str(imagehash.phash(pil_image))


def compare_phash(hash_a: str, hash_b: str) -> int:
    if not hash_a or not hash_b:
        raise ValueError("hash_a and hash_b must be non-empty strings")

    phash_a = imagehash.hex_to_hash(hash_a)
    phash_b = imagehash.hex_to_hash(hash_b)
    return int(phash_a - phash_b)


def compute_region_phashes(preprocessed_tag: PreprocessedTag) -> RegionPHash:
    return RegionPHash(
        canvas_hash=compute_phash(preprocessed_tag.canvas),
        primary_hash=compute_phash(preprocessed_tag.primary_region),
        support_hash=compute_phash(preprocessed_tag.support_region),
    )
