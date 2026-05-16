from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cbor2
import cv2
import numpy as np

from .layout import ARUCO_MARKER_IDS, Rect, TagLayout, build_tag_layout, infer_tag_layout


_DETECTED_QR_TO_PANEL_SCALE = 1.2
_PRIMARY_MIN_LAPLACIAN_VARIANCE = 150.0
_PRIMARY_MIN_CONTRAST_STD = 10.0
_CANVAS_MIN_MEAN_INTENSITY = 20.0
_CANVAS_MAX_MEAN_INTENSITY = 245.0
_MIN_QR_SIDE_LENGTH_PX = 120.0
_ECC_TERMINATION = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-6)
_ECC_BACKGROUND = (244, 240, 232)
_ARUCO_DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


class LocalizationError(ValueError):
    """Raised when a tag cannot be localized reliably."""


class ImageQualityError(LocalizationError):
    """Raised when an image is too poor to trust for enrolment or verification."""


@dataclass(frozen=True)
class QRDetection:
    corners: np.ndarray
    payload: str | None
    method: str
    qr_side_length_px: float


@dataclass(frozen=True)
class TagQuality:
    primary_laplacian_variance: float
    primary_contrast_std: float
    canvas_mean_intensity: float
    qr_side_length_px: float
    aruco_marker_count: int
    ecc_correlation: float | None


@dataclass(frozen=True)
class PreprocessedTag:
    canvas: np.ndarray
    primary_region: np.ndarray
    support_region: np.ndarray
    payload_uri: str | None
    alignment_method: str
    quality: TagQuality


def _load_image(image_source: str | bytes | np.ndarray) -> np.ndarray:
    if isinstance(image_source, str):
        image = cv2.imread(str(Path(image_source)), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Unable to load image from path: {image_source}")
        return image

    if isinstance(image_source, bytes):
        buffer = np.frombuffer(image_source, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Unable to decode image from bytes input")
        return image

    if isinstance(image_source, np.ndarray):
        if image_source.ndim == 2:
            return cv2.cvtColor(image_source, cv2.COLOR_GRAY2BGR)

        if image_source.ndim == 3 and image_source.shape[2] == 3:
            if image_source.dtype == np.uint8:
                return image_source.copy()
            return np.clip(image_source, 0, 255).astype(np.uint8)

        if image_source.ndim == 3 and image_source.shape[2] == 4:
            converted = image_source
            if converted.dtype != np.uint8:
                converted = np.clip(converted, 0, 255).astype(np.uint8)
            return cv2.cvtColor(converted, cv2.COLOR_BGRA2BGR)

        raise ValueError("NumPy image input must be grayscale, BGR, or BGRA")

    raise TypeError("image_source must be a file path, raw bytes, or numpy array")


def _order_points(points: np.ndarray) -> np.ndarray:
    reshaped = points.reshape(4, 2).astype(np.float32)
    ordered = np.zeros((4, 2), dtype=np.float32)

    sums = reshaped.sum(axis=1)
    diffs = np.diff(reshaped, axis=1).reshape(-1)

    ordered[0] = reshaped[np.argmin(sums)]
    ordered[2] = reshaped[np.argmax(sums)]
    ordered[1] = reshaped[np.argmin(diffs)]
    ordered[3] = reshaped[np.argmax(diffs)]
    return ordered


def _build_qr_detector() -> cv2.QRCodeDetector:
    detector = cv2.QRCodeDetector()
    if hasattr(detector, "setUseAlignmentMarkers"):
        detector.setUseAlignmentMarkers(True)
    return detector


def _normalize_detection_points(points: object) -> np.ndarray | None:
    if points is None:
        return None

    if isinstance(points, tuple):
        if len(points) != 1:
            return None
        points = points[0]

    array = np.asarray(points, dtype=np.float32)
    if array.size != 8:
        return None
    return array.reshape(4, 2)


def _qr_side_length(points: np.ndarray) -> float:
    ordered = _order_points(points)
    top = float(np.linalg.norm(ordered[1] - ordered[0]))
    right = float(np.linalg.norm(ordered[2] - ordered[1]))
    bottom = float(np.linalg.norm(ordered[2] - ordered[3]))
    left = float(np.linalg.norm(ordered[3] - ordered[0]))
    return max(top, right, bottom, left)


def _detect_with_wechat(image: np.ndarray) -> QRDetection | None:
    if not hasattr(cv2, "wechat_qrcode_WeChatQRCode"):
        return None

    try:
        detector = cv2.wechat_qrcode_WeChatQRCode()
        payloads, points = detector.detectAndDecode(image)
    except cv2.error:
        return None

    normalized = _normalize_detection_points(points)
    if normalized is None:
        return None

    payload: str | None = None
    if isinstance(payloads, (list, tuple)) and payloads:
        payload = payloads[0] or None

    return QRDetection(
        corners=normalized,
        payload=payload,
        method="wechat_qrcode",
        qr_side_length_px=_qr_side_length(normalized),
    )


def _detect_with_opencv(image: np.ndarray) -> QRDetection | None:
    detector = _build_qr_detector()

    for candidate_name, candidate in (("opencv_qrcode", image), ("opencv_qrcode_gray", cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))):
        payload, points, _ = detector.detectAndDecode(candidate)
        normalized = _normalize_detection_points(points)
        if normalized is not None:
            return QRDetection(
                corners=normalized,
                payload=payload or None,
                method=candidate_name,
                qr_side_length_px=_qr_side_length(normalized),
            )

        payload, points, _ = detector.detectAndDecodeCurved(candidate)
        normalized = _normalize_detection_points(points)
        if normalized is not None:
            return QRDetection(
                corners=normalized,
                payload=payload or None,
                method=f"{candidate_name}_curved",
                qr_side_length_px=_qr_side_length(normalized),
            )

        found, points = detector.detect(candidate)
        if found:
            normalized = _normalize_detection_points(points)
            if normalized is not None:
                return QRDetection(
                    corners=normalized,
                    payload=None,
                    method=f"{candidate_name}_detect_only",
                    qr_side_length_px=_qr_side_length(normalized),
                )

    return None


def _detect_qr(image: np.ndarray, require_payload: bool) -> QRDetection:
    detections = (_detect_with_wechat(image), _detect_with_opencv(image))

    for detection in detections:
        if detection is None:
            continue
        if require_payload and not detection.payload:
            continue
        return detection

    if require_payload:
        raise LocalizationError("unable to decode QR payload from image")
    raise LocalizationError("unable to localize tag from image")


def _build_layout_from_qr(detection: QRDetection) -> TagLayout:
    ordered = _order_points(detection.corners)
    top_width = np.linalg.norm(ordered[1] - ordered[0])
    bottom_width = np.linalg.norm(ordered[2] - ordered[3])
    left_height = np.linalg.norm(ordered[3] - ordered[0])
    right_height = np.linalg.norm(ordered[2] - ordered[1])

    detected_qr_width = max(int(round(max(top_width, bottom_width))), 1)
    detected_qr_height = max(int(round(max(left_height, right_height))), 1)
    qr_width = max(int(round(detected_qr_width * _DETECTED_QR_TO_PANEL_SCALE)), 1)
    qr_height = max(int(round(detected_qr_height * _DETECTED_QR_TO_PANEL_SCALE)), 1)
    return build_tag_layout(qr_width, qr_height)


def _align_from_qr(image: np.ndarray, detection: QRDetection, layout: TagLayout) -> np.ndarray:
    src = _order_points(detection.corners)

    detected_qr_width = max(int(round(np.linalg.norm(src[1] - src[0]))), 1)
    detected_qr_height = max(int(round(np.linalg.norm(src[3] - src[0]))), 1)
    quiet_x = (layout.qr_panel.width - detected_qr_width) / 2.0
    quiet_y = (layout.qr_panel.height - detected_qr_height) / 2.0

    dst = np.array(
        [
            [layout.qr_panel.x + quiet_x, layout.qr_panel.y + quiet_y],
            [layout.qr_panel.x + quiet_x + detected_qr_width - 1.0, layout.qr_panel.y + quiet_y],
            [
                layout.qr_panel.x + quiet_x + detected_qr_width - 1.0,
                layout.qr_panel.y + quiet_y + detected_qr_height - 1.0,
            ],
            [layout.qr_panel.x + quiet_x, layout.qr_panel.y + quiet_y + detected_qr_height - 1.0],
        ],
        dtype=np.float32,
    )

    transform = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, transform, (layout.canvas_width, layout.canvas_height))


def _build_aruco_detector() -> cv2.aruco.ArucoDetector:
    parameters = cv2.aruco.DetectorParameters()
    return cv2.aruco.ArucoDetector(_ARUCO_DICTIONARY, parameters)


def _detect_aruco_markers(image: np.ndarray) -> dict[int, np.ndarray]:
    detector = _build_aruco_detector()
    corners, ids, _ = detector.detectMarkers(image)
    if ids is None:
        return {}
    marker_map: dict[int, np.ndarray] = {}
    for marker_corners, marker_id in zip(corners, ids.reshape(-1), strict=True):
        marker_map[int(marker_id)] = np.asarray(marker_corners, dtype=np.float32).reshape(4, 2)
    return marker_map


def _marker_dst_points(layout: TagLayout) -> dict[int, np.ndarray]:
    marker_rects = {
        ARUCO_MARKER_IDS["top_left"]: layout.aruco_top_left,
        ARUCO_MARKER_IDS["top_right"]: layout.aruco_top_right,
        ARUCO_MARKER_IDS["bottom_right"]: layout.aruco_bottom_right,
        ARUCO_MARKER_IDS["bottom_left"]: layout.aruco_bottom_left,
    }
    mapping: dict[int, np.ndarray] = {}
    for marker_id, rect in marker_rects.items():
        mapping[marker_id] = np.array(
            [
                [rect.x, rect.y],
                [rect.x + rect.width - 1.0, rect.y],
                [rect.x + rect.width - 1.0, rect.y + rect.height - 1.0],
                [rect.x, rect.y + rect.height - 1.0],
            ],
            dtype=np.float32,
        )
    return mapping


def _refine_with_aruco(aligned_image: np.ndarray, layout: TagLayout) -> tuple[np.ndarray, int]:
    marker_map = _detect_aruco_markers(aligned_image)
    target_points = _marker_dst_points(layout)

    src_points: list[np.ndarray] = []
    dst_points: list[np.ndarray] = []
    for marker_id, dst in target_points.items():
        if marker_id not in marker_map:
            continue
        src_points.append(marker_map[marker_id])
        dst_points.append(dst)

    marker_count = len(src_points)
    if marker_count < 2:
        return aligned_image, marker_count

    src = np.concatenate(src_points, axis=0).astype(np.float32)
    dst = np.concatenate(dst_points, axis=0).astype(np.float32)
    homography, _ = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if homography is None:
        return aligned_image, marker_count

    refined = cv2.warpPerspective(aligned_image, homography, (layout.canvas_width, layout.canvas_height))
    return refined, marker_count


def _decode_payload_bytes(payload_uri: str) -> tuple[bytes, str]:
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
    return cbor_bytes, product_id


def _generate_template_image(payload_uri: str) -> np.ndarray | None:
    from .generator import generate_qr

    try:
        cbor_bytes, product_id = _decode_payload_bytes(payload_uri)
    except (ValueError, TypeError, cbor2.CBORDecodeError):
        return None
    template_bytes = generate_qr(cbor_bytes, product_id)
    image = cv2.imdecode(np.frombuffer(template_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    return image


def _refine_with_ecc(aligned_image: np.ndarray, template_image: np.ndarray) -> tuple[np.ndarray, float | None]:
    if aligned_image.shape[:2] != template_image.shape[:2]:
        return aligned_image, None

    template_gray = cv2.cvtColor(template_image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    image_gray = cv2.cvtColor(aligned_image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    warp_matrix = np.eye(2, 3, dtype=np.float32)

    try:
        correlation, warp_matrix = cv2.findTransformECC(
            template_gray,
            image_gray,
            warp_matrix,
            cv2.MOTION_AFFINE,
            _ECC_TERMINATION,
        )
    except cv2.error:
        return aligned_image, None

    refined = cv2.warpAffine(
        aligned_image,
        warp_matrix,
        (aligned_image.shape[1], aligned_image.shape[0]),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=_ECC_BACKGROUND,
    )
    return refined, float(correlation)


def _refine_with_payload_template(aligned_image: np.ndarray, payload_uri: str | None) -> tuple[np.ndarray, float | None]:
    if payload_uri is None:
        return aligned_image, None

    template_image = _generate_template_image(payload_uri)
    if template_image is None:
        return aligned_image, None

    return _refine_with_ecc(aligned_image, template_image)


def _crop_rect(image: np.ndarray, rect: Rect) -> np.ndarray:
    height, width = image.shape[:2]
    x0 = max(rect.x, 0)
    y0 = max(rect.y, 0)
    x1 = min(rect.x + rect.width, width)
    y1 = min(rect.y + rect.height, height)
    if x0 >= x1 or y0 >= y1:
        raise ValueError("crop rectangle does not intersect the image")
    return image[y0:y1, x0:x1]


def _resize_square(image: np.ndarray, size: int) -> np.ndarray:
    return cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)


def _support_column_rect(layout: TagLayout) -> Rect:
    top = layout.red_fragment.y
    bottom = layout.blue_fragment.y + layout.blue_fragment.height
    return Rect(
        x=layout.red_fragment.x,
        y=top,
        width=layout.red_fragment.width,
        height=bottom - top,
    )


def _compute_quality(
    *,
    primary_region: np.ndarray,
    canvas: np.ndarray,
    detection: QRDetection,
    aruco_marker_count: int,
    ecc_correlation: float | None,
) -> TagQuality:
    return TagQuality(
        primary_laplacian_variance=float(cv2.Laplacian(primary_region, cv2.CV_64F).var()),
        primary_contrast_std=float(primary_region.std()),
        canvas_mean_intensity=float(canvas.mean()),
        qr_side_length_px=detection.qr_side_length_px,
        aruco_marker_count=aruco_marker_count,
        ecc_correlation=ecc_correlation,
    )


def _validate_quality(quality: TagQuality) -> None:
    problems: list[str] = []

    if quality.qr_side_length_px < _MIN_QR_SIDE_LENGTH_PX:
        problems.append("move closer so the tag occupies more of the frame")
    if quality.primary_laplacian_variance < _PRIMARY_MIN_LAPLACIAN_VARIANCE:
        problems.append("image is too blurry")
    if quality.primary_contrast_std < _PRIMARY_MIN_CONTRAST_STD:
        problems.append("image has too little contrast")
    if quality.canvas_mean_intensity < _CANVAS_MIN_MEAN_INTENSITY:
        problems.append("image is too dark")
    if quality.canvas_mean_intensity > _CANVAS_MAX_MEAN_INTENSITY:
        problems.append("image is too bright")

    if problems:
        raise ImageQualityError("image isn't clear enough: " + "; ".join(problems))


def _preprocess_core(
    image_source: str | bytes | np.ndarray,
    anchor_size: int,
    apply_clahe: bool,
    require_payload: bool,
) -> PreprocessedTag:
    if anchor_size <= 0:
        raise ValueError("anchor_size must be a positive integer")

    bgr_image = _load_image(image_source)
    detection = _detect_qr(bgr_image, require_payload=require_payload)
    return _preprocess_detected_tag(
        bgr_image,
        detection,
        anchor_size=anchor_size,
        apply_clahe=apply_clahe,
    )


def _preprocess_detected_tag(
    bgr_image: np.ndarray,
    detection: QRDetection,
    *,
    anchor_size: int,
    apply_clahe: bool,
) -> PreprocessedTag:
    layout = _build_layout_from_qr(detection)
    aligned_image = _align_from_qr(bgr_image, detection, layout)

    aruco_refined_image, aruco_marker_count = _refine_with_aruco(aligned_image, layout)

    ecc_correlation: float | None = None
    final_image = aruco_refined_image
    if detection.payload:
        final_image, ecc_correlation = _refine_with_payload_template(aruco_refined_image, detection.payload)

    payload_uri = detection.payload
    if payload_uri is None:
        try:
            payload_uri = _detect_qr(final_image, require_payload=True).payload
        except LocalizationError:
            payload_uri = None

    if ecc_correlation is None and payload_uri is not None:
        refined_image, refined_correlation = _refine_with_payload_template(final_image, payload_uri)
        if refined_correlation is not None:
            final_image = refined_image
            ecc_correlation = refined_correlation

    grayscale = cv2.cvtColor(final_image, cv2.COLOR_BGR2GRAY)
    canvas = np.ascontiguousarray(grayscale, dtype=np.uint8)

    inferred_layout = infer_tag_layout(canvas.shape[1], canvas.shape[0])
    primary_region = _resize_square(_crop_rect(canvas, inferred_layout.qr_panel), anchor_size)
    support_region = _resize_square(_crop_rect(canvas, _support_column_rect(inferred_layout)), anchor_size)

    if apply_clahe:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        primary_region = clahe.apply(primary_region)

    primary_region = np.ascontiguousarray(primary_region, dtype=np.uint8)
    support_region = np.ascontiguousarray(support_region, dtype=np.uint8)
    quality = _compute_quality(
        primary_region=primary_region,
        canvas=canvas,
        detection=detection,
        aruco_marker_count=aruco_marker_count,
        ecc_correlation=ecc_correlation,
    )
    _validate_quality(quality)

    alignment_method = detection.method
    if aruco_marker_count >= 2:
        alignment_method += "+aruco"
    if ecc_correlation is not None:
        alignment_method += "+ecc"

    return PreprocessedTag(
        canvas=canvas,
        primary_region=primary_region,
        support_region=support_region,
        payload_uri=payload_uri,
        alignment_method=alignment_method,
        quality=quality,
    )


def preprocess_tag(
    image_source: str | bytes | np.ndarray,
    anchor_size: int = 256,
    apply_clahe: bool = True,
) -> PreprocessedTag:
    return _preprocess_core(
        image_source=image_source,
        anchor_size=anchor_size,
        apply_clahe=apply_clahe,
        require_payload=False,
    )


def preprocess(
    image_source: str | bytes | np.ndarray,
    anchor_size: int = 256,
    apply_clahe: bool = True,
) -> np.ndarray:
    return preprocess_tag(
        image_source=image_source,
        anchor_size=anchor_size,
        apply_clahe=apply_clahe,
    ).primary_region


def extract_reference_patches(
    image_source: str | bytes | np.ndarray,
    patch_size: int = 96,
) -> dict[str, np.ndarray]:
    if patch_size <= 0:
        raise ValueError("patch_size must be a positive integer")

    bgr_image = _load_image(image_source)
    detection = _detect_qr(bgr_image, require_payload=False)
    layout = _build_layout_from_qr(detection)
    aligned_image = _align_from_qr(bgr_image, detection, layout)
    aligned_image, _ = _refine_with_aruco(aligned_image, layout)
    payload_uri = detection.payload
    if payload_uri is None:
        try:
            payload_uri = _detect_qr(aligned_image, require_payload=True).payload
        except LocalizationError:
            payload_uri = None
    aligned_image, _ = _refine_with_payload_template(aligned_image, payload_uri)

    patches: dict[str, np.ndarray] = {}

    for name, rect in (
        ("red", layout.red_fragment),
        ("green", layout.green_fragment),
        ("blue", layout.blue_fragment),
    ):
        patch = _crop_rect(aligned_image, rect)
        patch = cv2.resize(patch, (patch_size, patch_size), interpolation=cv2.INTER_AREA)
        patches[name] = np.ascontiguousarray(patch, dtype=np.uint8)

    return patches


def decode_qr_payload(image_source: str | bytes | np.ndarray) -> str:
    image = _load_image(image_source)
    detection = _detect_qr(image, require_payload=True)
    if detection.payload is None:
        raise LocalizationError("unable to decode QR payload from image")
    return detection.payload


def decode_qr_payload_bytes(image_source: str | bytes | np.ndarray) -> tuple[bytes, str]:
    return _decode_payload_bytes(decode_qr_payload(image_source))
