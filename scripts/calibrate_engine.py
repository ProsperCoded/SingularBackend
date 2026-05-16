from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.engine.bundle import verify_enrolment_bundle
from services.engine.preprocessor import ImageQualityError, LocalizationError


def _load_product_from_sqlite(db_path: Path, product_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(str(db_path))
    try:
        cursor = connection.execute(
            "SELECT id, enrolment_bundle, status, product_type, vendor_id, brand_id, transaction_ref "
            "FROM product WHERE id = ?",
            (product_id,),
        )
        row = cursor.fetchone()
    finally:
        connection.close()

    if row is None:
        raise ValueError(f"product_id {product_id!r} not found in sqlite db {db_path}")

    enrolment_bundle = row[1]
    if enrolment_bundle is None:
        raise ValueError(f"product_id {product_id!r} does not have an enrolment_bundle")

    return {
        "id": row[0],
        "enrolment_bundle": json.loads(enrolment_bundle),
        "status": row[2],
        "product_type": row[3],
        "vendor_id": row[4],
        "brand_id": row[5],
        "transaction_ref": row[6],
    }


def _load_product_from_json(json_path: Path, product_id: str | None) -> dict[str, Any]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        records = payload
    else:
        records = [payload]

    if product_id is None:
        if len(records) != 1:
            raise ValueError("product json contains multiple records; pass --product-id to select one")
        record = records[0]
    else:
        try:
            record = next(item for item in records if item.get("id") == product_id)
        except StopIteration as exc:
            raise ValueError(f"product_id {product_id!r} not found in json file {json_path}") from exc

    bundle = record.get("enrolment_bundle")
    if not isinstance(bundle, dict):
        raise ValueError("selected product record does not contain a valid enrolment_bundle object")
    return record


def _iter_labeled_images(folder: Path, label: str) -> list[tuple[str, Path]]:
    return [(label, path) for path in sorted(folder.iterdir()) if path.is_file()]


def _evaluate_image(bundle: dict[str, Any], label: str, image_path: Path) -> dict[str, Any]:
    try:
        summary = verify_enrolment_bundle(bundle, str(image_path))
    except (ImageQualityError, LocalizationError) as exc:
        return {
            "label": label,
            "file": image_path.name,
            "path": str(image_path),
            "result_type": "SKIPPED",
            "verdict": None,
            "score": None,
            "lbp_similarity": None,
            "sharpness_score": None,
            "sharpness_ratio": None,
            "vector_similarity": None,
            "mean_vector_similarity": None,
            "primary_phash_distance": None,
            "support_phash_distance": None,
            "canvas_phash_distance": None,
            "color_distance": None,
            "query_halftone_mean": None,
            "query_halftone_max": None,
            "structural_verdict": None,
            "color_verdict": None,
            "verdict_reasons": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    except Exception as exc:  # pragma: no cover - calibration should surface unexpected failures
        return {
            "label": label,
            "file": image_path.name,
            "path": str(image_path),
            "result_type": "ERROR",
            "verdict": None,
            "score": None,
            "lbp_similarity": None,
            "sharpness_score": None,
            "sharpness_ratio": None,
            "vector_similarity": None,
            "mean_vector_similarity": None,
            "primary_phash_distance": None,
            "support_phash_distance": None,
            "canvas_phash_distance": None,
            "color_distance": None,
            "query_halftone_mean": None,
            "query_halftone_max": None,
            "structural_verdict": None,
            "color_verdict": None,
            "verdict_reasons": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }

    return {
        "label": label,
        "file": image_path.name,
        "path": str(image_path),
        "result_type": "VERDICT",
        "verdict": summary.verdict,
        "score": summary.composite_score,
        "lbp_similarity": summary.lbp_score,
        "sharpness_score": summary.sharpness_score,
        "sharpness_ratio": summary.sharpness_ratio,
        "vector_similarity": summary.vector_score,
        "mean_vector_similarity": summary.mean_vector_score,
        "primary_phash_distance": summary.primary_phash_distance,
        "support_phash_distance": summary.support_phash_distance,
        "canvas_phash_distance": summary.canvas_phash_distance,
        "color_distance": summary.color_distance,
        "query_halftone_mean": summary.query_halftone_mean,
        "query_halftone_max": summary.query_halftone_max,
        "structural_verdict": summary.structural_verdict,
        "color_verdict": summary.color_verdict,
        "verdict_reasons": ",".join(summary.verdict_reasons),
        "error_type": None,
        "error_message": None,
    }


def _class_summary(rows: list[dict[str, Any]], label: str) -> Counter:
    relevant = [row for row in rows if row["label"] == label]
    counter: Counter[str] = Counter()
    for row in relevant:
        if row["result_type"] == "VERDICT":
            counter[str(row["verdict"])] += 1
        else:
            counter[str(row["result_type"])] += 1
    return counter


def _render_markdown(
    *,
    product_record: dict[str, Any],
    rows: list[dict[str, Any]],
    csv_path: Path,
    generated_at: str,
) -> str:
    correct_summary = _class_summary(rows, "correct")
    wrong_summary = _class_summary(rows, "wrong")
    false_authentic_wrong = sum(1 for row in rows if row["label"] == "wrong" and row["verdict"] == "pass")
    false_fake_correct = sum(1 for row in rows if row["label"] == "correct" and row["verdict"] == "fail")

    lines = [
        "# Calibration Baseline Report",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Product ID: `{product_record['id']}`",
        f"- Product Type: `{product_record['product_type']}`",
        f"- Source CSV: `{csv_path.name}`",
        "",
        "## Summary",
        "",
        f"- Correct images: `{sum(1 for row in rows if row['label'] == 'correct')}`",
        f"- Wrong images: `{sum(1 for row in rows if row['label'] == 'wrong')}`",
        f"- Wrong images classified `AUTHENTIC`: `{false_authentic_wrong}`",
        f"- Correct images classified `FAKE`: `{false_fake_correct}`",
        "",
        "### Correct Folder Outcome Counts",
    ]

    for key, value in sorted(correct_summary.items()):
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "### Wrong Folder Outcome Counts"])
    for key, value in sorted(wrong_summary.items()):
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Per-Image Results",
            "",
            "| Label | File | Result | Score | LBP | Sharpness Ratio | Vector | Primary pHash | Color | Reasons / Error |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for row in rows:
        detail = row["verdict_reasons"] or row["error_message"] or ""
        score = "" if row["score"] is None else f"{row['score']:.2f}"
        lbp = "" if row["lbp_similarity"] is None else f"{row['lbp_similarity']:.4f}"
        sharpness_ratio = "" if row["sharpness_ratio"] is None else f"{row['sharpness_ratio']:.4f}"
        vector = "" if row["vector_similarity"] is None else f"{row['vector_similarity']:.4f}"
        primary = "" if row["primary_phash_distance"] is None else str(row["primary_phash_distance"])
        color = "" if row["color_distance"] is None else f"{row['color_distance']:.4f}"
        result = row["verdict"] if row["result_type"] == "VERDICT" else row["result_type"]
        lines.append(
            f"| `{row['label']}` | `{row['file']}` | `{result}` | `{score}` | `{lbp}` | `{sharpness_ratio}` | `{vector}` | `{primary}` | `{color}` | {detail} |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run engine calibration against labeled image folders.")
    parser.add_argument("--sqlite-db", help="Path to sqlite database file.")
    parser.add_argument("--product-json", help="Path to exported product record JSON.")
    parser.add_argument("--product-id", help="Product ID to evaluate against.")
    parser.add_argument("--correct-dir", required=True, help="Folder containing genuine/correct scans.")
    parser.add_argument("--wrong-dir", required=True, help="Folder containing cloned/wrong scans.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/calibration",
        help="Directory for CSV and markdown reports.",
    )
    args = parser.parse_args()

    correct_dir = Path(args.correct_dir).resolve()
    wrong_dir = Path(args.wrong_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.sqlite_db and not args.product_json:
        raise ValueError("pass either --sqlite-db or --product-json")

    if args.product_json:
        product_record = _load_product_from_json(Path(args.product_json).resolve(), args.product_id)
    else:
        if not args.product_id:
            raise ValueError("--product-id is required when using --sqlite-db")
        product_record = _load_product_from_sqlite(Path(args.sqlite_db).resolve(), args.product_id)

    bundle = product_record["enrolment_bundle"]

    labeled_paths = _iter_labeled_images(correct_dir, "correct") + _iter_labeled_images(wrong_dir, "wrong")
    rows: list[dict[str, Any]] = []
    total = len(labeled_paths)
    for index, (label, image_path) in enumerate(labeled_paths, start=1):
        print(f"[{index}/{total}] evaluating {label}:{image_path.name}", flush=True)
        row = _evaluate_image(bundle, label, image_path)
        result = row["verdict"] if row["result_type"] == "VERDICT" else row["result_type"]
        print(f"[{index}/{total}] result {label}:{image_path.name} -> {result}", flush=True)
        rows.append(row)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stem = f"calibration_{product_record['id']}_{timestamp}"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    report = _render_markdown(
        product_record=product_record,
        rows=rows,
        csv_path=csv_path,
        generated_at=timestamp,
    )
    md_path.write_text(report, encoding="utf-8")

    print(json.dumps({"csv": str(csv_path), "markdown": str(md_path)}, indent=2))


if __name__ == "__main__":
    main()
