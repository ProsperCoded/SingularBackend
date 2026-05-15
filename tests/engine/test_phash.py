from __future__ import annotations

import re

import numpy as np

from engine.generator import generate_qr
from engine.phash import (
    PHASH_THRESHOLD,
    SUPPORT_PHASH_THRESHOLD,
    compare_phash,
    compute_phash,
    compute_region_phashes,
)
from engine.preprocessor import preprocess_tag
from scripts.manual_artifacts import save_bytes


def test_compute_phash_returns_16_character_hex_string() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)

    phash = compute_phash(image)

    assert len(phash) == 16
    assert re.fullmatch(r"[0-9a-f]{16}", phash) is not None


def test_compare_phash_same_image_is_zero() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)

    hash_a = compute_phash(image)
    hash_b = compute_phash(image)

    assert compare_phash(hash_a, hash_b) == 0


def test_compare_phash_distinguishes_structurally_different_images() -> None:
    blank = np.zeros((256, 256), dtype=np.uint8)
    checkerboard = ((np.indices((256, 256)).sum(axis=0) % 2) * 255).astype(np.uint8)

    blank_hash = compute_phash(blank)
    checkerboard_hash = compute_phash(checkerboard)

    assert compare_phash(blank_hash, checkerboard_hash) > PHASH_THRESHOLD


def test_phash_output_can_be_saved_for_manual_inspection() -> None:
    image = np.random.randint(0, 256, size=(256, 256), dtype=np.uint8)

    phash = compute_phash(image)
    output_path = save_bytes(phash.encode("ascii"), "phash-stage4-test.txt")

    assert output_path.exists()
    assert output_path.read_text(encoding="ascii") == phash


def test_compute_region_phashes_returns_split_hashes() -> None:
    png_bytes = generate_qr(b"example-cbor-payload", "product-test-1")

    region_hashes = compute_region_phashes(preprocess_tag(png_bytes))

    assert len(region_hashes.canvas_hash) == 16
    assert len(region_hashes.primary_hash) == 16
    assert len(region_hashes.support_hash) == 16


def test_support_region_uses_looser_threshold_than_primary() -> None:
    assert SUPPORT_PHASH_THRESHOLD > PHASH_THRESHOLD
