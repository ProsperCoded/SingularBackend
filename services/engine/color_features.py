from __future__ import annotations

import cv2
import numpy as np

from .generator import generate_qr
from .preprocessor import decode_qr_payload_bytes
from .preprocessor import extract_reference_patches


PATCH_NAMES = ("red", "green", "blue")
COLOR_SIGNATURE_VERSION_LEGACY = "v1"
COLOR_SIGNATURE_VERSION_CURRENT = "v2"


def _gray_world_white_balance(patches: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    stacked = np.concatenate([patch.reshape(-1, 3).astype(np.float32) for patch in patches.values()], axis=0)
    channel_means = stacked.mean(axis=0)
    gray_level = float(channel_means.mean())
    safe_means = np.clip(channel_means, 1.0, None)
    gains = gray_level / safe_means

    balanced: dict[str, np.ndarray] = {}
    for name, patch in patches.items():
        corrected = np.clip(patch.astype(np.float32) * gains.reshape(1, 1, 3), 0, 255).astype(np.uint8)
        balanced[name] = corrected
    return balanced


def _build_reference_patches(
    image_source: str | bytes | np.ndarray,
    patch_size: int,
) -> dict[str, np.ndarray] | None:
    try:
        cbor_payload, product_id = decode_qr_payload_bytes(image_source)
    except Exception:
        return None

    qr_png = generate_qr(cbor_payload, product_id)
    template_image = cv2.imdecode(np.frombuffer(qr_png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if template_image is None:
        return None
    return extract_reference_patches(template_image, patch_size=patch_size)


def _reference_guided_balance(
    observed_patches: dict[str, np.ndarray],
    reference_patches: dict[str, np.ndarray] | None,
) -> dict[str, np.ndarray]:
    if reference_patches is None:
        return _gray_world_white_balance(observed_patches)

    observed_stack = np.concatenate(
        [observed_patches[name].reshape(-1, 3).astype(np.float32) for name in PATCH_NAMES],
        axis=0,
    )
    reference_stack = np.concatenate(
        [reference_patches[name].reshape(-1, 3).astype(np.float32) for name in PATCH_NAMES],
        axis=0,
    )
    observed_mean = observed_stack.mean(axis=0)
    reference_mean = reference_stack.mean(axis=0)
    gains = reference_mean / np.clip(observed_mean, 1.0, None)

    corrected: dict[str, np.ndarray] = {}
    for name, patch in observed_patches.items():
        balanced = np.clip(patch.astype(np.float32) * gains.reshape(1, 1, 3), 0, 255).astype(np.uint8)
        corrected[name] = balanced
    return corrected


def _rgb_chromaticity(mean_bgr: np.ndarray) -> np.ndarray:
    rgb = mean_bgr[::-1].astype(np.float32)
    total = float(np.clip(rgb.sum(), 1e-6, None))
    return rgb / total


def _luminance(mean_bgr: np.ndarray) -> float:
    blue, green, red = mean_bgr.astype(np.float32)
    return float((0.114 * blue) + (0.587 * green) + (0.299 * red))


def _extract_color_signature_v1(image_source: str | bytes | np.ndarray, patch_size: int = 64) -> np.ndarray:
    patches = extract_reference_patches(image_source, patch_size=patch_size)

    values: list[float] = []
    for name in PATCH_NAMES:
        patch = patches[name]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)

        saturation = hsv[:, :, 1].astype(np.float32)
        a_channel = lab[:, :, 1].astype(np.float32)
        b_channel = lab[:, :, 2].astype(np.float32)

        values.extend(
            [
                float(saturation.mean() / 255.0),
                float(saturation.std() / 255.0),
                float((a_channel.mean() - 128.0) / 127.0),
                float((b_channel.mean() - 128.0) / 127.0),
            ]
        )

    return np.asarray(values, dtype=np.float32)


def _extract_color_signature_v2(image_source: str | bytes | np.ndarray, patch_size: int = 64) -> np.ndarray:
    observed_patches = extract_reference_patches(image_source, patch_size=patch_size)
    reference_patches = _build_reference_patches(image_source, patch_size=patch_size)
    patches = _reference_guided_balance(observed_patches, reference_patches)

    values: list[float] = []
    patch_means_bgr: dict[str, np.ndarray] = {}
    patch_means_lab: dict[str, np.ndarray] = {}
    patch_luminance: dict[str, float] = {}
    reference_means_lab: dict[str, np.ndarray] = {}

    if reference_patches is not None:
        for name in PATCH_NAMES:
            reference_lab = cv2.cvtColor(reference_patches[name], cv2.COLOR_BGR2LAB)
            reference_means_lab[name] = reference_lab.reshape(-1, 3).astype(np.float32).mean(axis=0)

    for name in PATCH_NAMES:
        patch = patches[name]
        lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
        mean_bgr = patch.reshape(-1, 3).astype(np.float32).mean(axis=0)
        mean_lab = lab.reshape(-1, 3).astype(np.float32).mean(axis=0)

        patch_means_bgr[name] = mean_bgr
        patch_means_lab[name] = mean_lab
        patch_luminance[name] = _luminance(mean_bgr)
        values.extend(_rgb_chromaticity(mean_bgr).tolist())
        if name in reference_means_lab:
            ref_lab = reference_means_lab[name]
            values.extend(
                [
                    float((mean_lab[0] - ref_lab[0]) / 100.0),
                    float((mean_lab[1] - ref_lab[1]) / 127.0),
                    float((mean_lab[2] - ref_lab[2]) / 127.0),
                ]
            )

    for left_name, right_name in (("red", "green"), ("red", "blue"), ("green", "blue")):
        left_lum = patch_luminance[left_name]
        right_lum = patch_luminance[right_name]
        values.append(float(np.log((left_lum + 1e-6) / (right_lum + 1e-6))))

        left_lab = patch_means_lab[left_name]
        right_lab = patch_means_lab[right_name]
        values.append(float(np.linalg.norm((left_lab - right_lab) / np.array([100.0, 127.0, 127.0], dtype=np.float32))))

    return np.asarray(values, dtype=np.float32)


def extract_color_signature(
    image_source: str | bytes | np.ndarray,
    patch_size: int = 64,
    descriptor_version: str = COLOR_SIGNATURE_VERSION_CURRENT,
) -> np.ndarray:
    if descriptor_version == COLOR_SIGNATURE_VERSION_LEGACY:
        return _extract_color_signature_v1(image_source, patch_size=patch_size)
    if descriptor_version == COLOR_SIGNATURE_VERSION_CURRENT:
        return _extract_color_signature_v2(image_source, patch_size=patch_size)
    raise ValueError(f"Unsupported color signature version: {descriptor_version}")


def compare_color_signatures(signature_a: np.ndarray, signature_b: np.ndarray) -> float:
    if signature_a.shape != signature_b.shape:
        raise ValueError("color signatures must share the same shape")
    return float(np.linalg.norm(signature_a.astype(np.float32) - signature_b.astype(np.float32)))


def infer_color_signature_version(signature: np.ndarray) -> str:
    if signature.ndim != 1:
        raise ValueError("color signature must be a 1D vector")

    if signature.shape[0] == 12:
        return COLOR_SIGNATURE_VERSION_LEGACY
    if signature.shape[0] == 24:
        return COLOR_SIGNATURE_VERSION_CURRENT

    raise ValueError(f"Unsupported color signature shape: {signature.shape}")
