from __future__ import annotations

import argparse
import base64
import json
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

from .pipeline import DEFAULT_ENROLMENT_SCAN_COUNT, EnrolResult, enrol, extract_features, generate_qr_only
from .preprocessor import ImageQualityError, LocalizationError, PreprocessedTag, decode_qr_payload, preprocess_tag
from .signer import verify_payload
from .bundle import serialize_enrolment_bundle, verify_enrolment_bundle


DEFAULT_OUTPUT_DIR = Path("artifacts/manual")


def _decode_qr_data(image_path: str | Path) -> bytes:
    payload_uri = decode_qr_payload(str(image_path))
    parsed = urlparse(payload_uri)
    if parsed.scheme != "printpuf":
        raise ValueError("Decoded QR does not use the printpuf scheme")

    params = parse_qs(parsed.query)
    encoded_payload = params.get("data", [None])[0]
    if not encoded_payload:
        raise ValueError("Decoded QR payload is missing the data parameter")

    return base64.urlsafe_b64decode(encoded_payload.encode("ascii"))


def _bundle_path(output_dir: Path) -> Path:
    return output_dir / "enrolment.json"


def _ensure_output_dir(output_dir: str | Path | None = None) -> Path:
    target = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def _save_png_bytes(png_bytes: bytes, filename: str, output_dir: str | Path | None = None) -> Path:
    target_dir = _ensure_output_dir(output_dir)
    output_path = target_dir / filename
    output_path.write_bytes(png_bytes)
    return output_path


def _save_image_array(image_array: np.ndarray, filename: str, output_dir: str | Path | None = None) -> Path:
    target_dir = _ensure_output_dir(output_dir)
    output_path = target_dir / filename
    image_to_write = image_array
    if image_to_write.dtype != np.uint8:
        image_to_write = np.clip(image_to_write, 0, 255).astype(np.uint8)
    if not cv2.imwrite(str(output_path), image_to_write):
        raise ValueError(f"Unable to write image to {output_path}")
    return output_path


def _save_enrolment_bundle(
    *,
    output_dir: Path,
    product_id: str,
    vendor_id: str | None,
    combined_vector: np.ndarray,
    combined_vectors: tuple[np.ndarray, ...],
    color_signature: np.ndarray,
    color_signatures: tuple[np.ndarray, ...],
    primary_phash_str: str,
    primary_phash_strs: tuple[str, ...],
    support_phash_str: str,
    support_phash_strs: tuple[str, ...],
    canvas_phash_str: str,
    canvas_phash_strs: tuple[str, ...],
    lbp_sketch: bytes,
    updated_qr_png_bytes: bytes,
    preprocessed_tags: tuple[PreprocessedTag, ...],
    scan_count: int,
) -> Path:
    _ensure_output_dir(output_dir)
    _save_png_bytes(updated_qr_png_bytes, "updated_qr.png", output_dir=output_dir)
    for index, tag in enumerate(preprocessed_tags, start=1):
        _save_image_array(tag.canvas, f"scan_{index}_canvas.png", output_dir=output_dir)
        _save_image_array(tag.primary_region, f"scan_{index}_primary_region.png", output_dir=output_dir)
        _save_image_array(tag.support_region, f"scan_{index}_support_region.png", output_dir=output_dir)

    bundle = {
        **serialize_enrolment_bundle(
            EnrolResult(
                product_id=product_id,
                combined_vector=combined_vector,
                combined_vectors=combined_vectors,
                color_signature=color_signature,
                color_signatures=color_signatures,
                primary_phash_str=primary_phash_str,
                primary_phash_strs=primary_phash_strs,
                support_phash_str=support_phash_str,
                support_phash_strs=support_phash_strs,
                canvas_phash_str=canvas_phash_str,
                canvas_phash_strs=canvas_phash_strs,
                lbp_sketch=lbp_sketch,
                updated_qr_png_bytes=updated_qr_png_bytes,
                scan_count=scan_count,
            ),
            vendor_id=vendor_id,
        ),
        "files": {
            "updated_qr_png": "updated_qr.png",
            "scan_artifacts": [
                {
                    "canvas_png": f"scan_{index}_canvas.png",
                    "primary_region_png": f"scan_{index}_primary_region.png",
                    "support_region_png": f"scan_{index}_support_region.png",
                }
                for index in range(1, scan_count + 1)
            ],
        },
    }
    bundle_path = _bundle_path(output_dir)
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    return bundle_path


def _load_enrolment_bundle(bundle_path: str | Path) -> dict[str, object]:
    return json.loads(Path(bundle_path).read_text(encoding="utf-8"))


def _cmd_generate(args: argparse.Namespace) -> int:
    result = generate_qr_only(args.product_id, args.vendor_id)
    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"{args.product_id}.png"
    _save_png_bytes(result.qr_png_bytes, output_path.name, output_dir=output_path.parent)
    print(json.dumps({"product_id": result.product_id, "qr_png": str(output_path)}, indent=2))
    return 0


def _cmd_scan_qr(args: argparse.Namespace) -> int:
    cbor_bytes = _decode_qr_data(args.image)
    payload = verify_payload(cbor_bytes)
    print(json.dumps({"pid": payload["pid"], "vid": payload["vid"], "verified": True}, indent=2))
    return 0


def _cmd_enrol(args: argparse.Namespace) -> int:
    result = enrol(args.image, args.product_id, args.vendor_id, required_scan_count=args.required_scan_count)
    preprocessed_tags = tuple(preprocess_tag(image_path) for image_path in args.image)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR / "enrolments" / args.product_id
    bundle_path = _save_enrolment_bundle(
        output_dir=output_dir,
        product_id=result.product_id,
        vendor_id=args.vendor_id,
        combined_vector=result.combined_vector,
        combined_vectors=result.combined_vectors,
        color_signature=result.color_signature,
        color_signatures=result.color_signatures,
        primary_phash_str=result.primary_phash_str,
        primary_phash_strs=result.primary_phash_strs,
        support_phash_str=result.support_phash_str,
        support_phash_strs=result.support_phash_strs,
        canvas_phash_str=result.canvas_phash_str,
        canvas_phash_strs=result.canvas_phash_strs,
        lbp_sketch=result.lbp_sketch,
        updated_qr_png_bytes=result.updated_qr_png_bytes,
        preprocessed_tags=preprocessed_tags,
        scan_count=result.scan_count,
    )
    print(json.dumps({"bundle": str(bundle_path), "output_dir": str(output_dir), "scan_count": result.scan_count}, indent=2))
    return 0


def _cmd_features(args: argparse.Namespace) -> int:
    result = extract_features(args.image)
    print(
        json.dumps(
            {
                "combined_vector_length": int(result.combined_vector.shape[0]),
                "color_signature_length": int(result.color_signature.shape[0]),
                "primary_phash_str": result.primary_phash_str,
                "support_phash_str": result.support_phash_str,
                "canvas_phash_str": result.canvas_phash_str,
            },
            indent=2,
        )
    )
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    report = verify_enrolment_bundle(_load_enrolment_bundle(args.bundle), args.image)
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.verdict != "fail" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine", description="PrintPUF manual test CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a QR PNG from the env-backed keypair")
    generate.add_argument("--product-id", required=True)
    generate.add_argument("--vendor-id")
    generate.add_argument("--output", help="Output PNG path")
    generate.set_defaults(func=_cmd_generate)

    scan_qr = subparsers.add_parser("scan-qr", help="Decode and verify a QR image")
    scan_qr.add_argument("--image", required=True)
    scan_qr.set_defaults(func=_cmd_scan_qr)

    enrol_parser = subparsers.add_parser("enrol", help="Process a photographed tag and write an enrolment bundle")
    enrol_parser.add_argument("--image", required=True, action="append")
    enrol_parser.add_argument("--product-id", required=True)
    enrol_parser.add_argument("--vendor-id")
    enrol_parser.add_argument("--output-dir", help="Directory for bundle and artifacts")
    enrol_parser.add_argument("--required-scan-count", type=int, default=DEFAULT_ENROLMENT_SCAN_COUNT)
    enrol_parser.set_defaults(func=_cmd_enrol)

    features = subparsers.add_parser("features", help="Extract and print feature summary for a scan")
    features.add_argument("--image", required=True)
    features.set_defaults(func=_cmd_features)

    verify_parser = subparsers.add_parser("verify", help="Compare a scan against an enrolment bundle")
    verify_parser.add_argument("--bundle", required=True)
    verify_parser.add_argument("--image", required=True)
    verify_parser.set_defaults(func=_cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ImageQualityError, LocalizationError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")
