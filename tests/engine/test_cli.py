from __future__ import annotations

import json

import cv2
import numpy as np

from engine.cli import main
from engine.layout import infer_tag_layout


def _desaturate_support_patches(image_path, output_path) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise AssertionError("expected generated image to be readable")

    layout = infer_tag_layout(image.shape[1], image.shape[0])
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    for rect in (layout.red_fragment, layout.green_fragment, layout.blue_fragment):
        patch = hsv[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]
        patch[:, :, 1] = np.clip(patch[:, :, 1] * 0.15, 0, 255).astype(np.uint8)
    washed_out = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    assert cv2.imwrite(str(output_path), washed_out)


def test_cli_generate_scan_enrol_and_verify_round_trip(tmp_path) -> None:
    tag_path = tmp_path / "tag.png"
    bundle_dir = tmp_path / "bundle"

    assert (
        main(
            [
                "generate",
                "--product-id",
                "product-test-1",
                "--vendor-id",
                "vendor-abc",
                "--output",
                str(tag_path),
            ]
        )
        == 0
    )
    assert tag_path.exists()

    assert main(["scan-qr", "--image", str(tag_path)]) == 0

    assert (
        main(
            [
                "enrol",
                "--image",
                str(tag_path),
                "--image",
                str(tag_path),
                "--image",
                str(tag_path),
                "--product-id",
                "product-test-1",
                "--vendor-id",
                "vendor-abc",
                "--output-dir",
                str(bundle_dir),
            ]
        )
        == 0
    )

    bundle_path = bundle_dir / "enrolment.json"
    assert bundle_path.exists()
    assert (bundle_dir / "updated_qr.png").exists()
    assert (bundle_dir / "scan_1_canvas.png").exists()
    assert (bundle_dir / "scan_2_canvas.png").exists()
    assert (bundle_dir / "scan_3_canvas.png").exists()
    assert (bundle_dir / "scan_1_primary_region.png").exists()
    assert (bundle_dir / "scan_2_primary_region.png").exists()
    assert (bundle_dir / "scan_3_primary_region.png").exists()
    assert (bundle_dir / "scan_1_support_region.png").exists()
    assert (bundle_dir / "scan_2_support_region.png").exists()
    assert (bundle_dir / "scan_3_support_region.png").exists()

    assert main(["verify", "--bundle", str(bundle_path), "--image", str(tag_path)]) == 0


def test_cli_verify_demotes_washed_out_support_colors(tmp_path, capsys) -> None:
    tag_path = tmp_path / "tag.png"
    bundle_dir = tmp_path / "bundle"
    washed_out_path = tmp_path / "tag-washed-out.png"

    assert (
        main(
            [
                "generate",
                "--product-id",
                "product-test-1",
                "--vendor-id",
                "vendor-abc",
                "--output",
                str(tag_path),
            ]
        )
        == 0
    )
    _desaturate_support_patches(tag_path, washed_out_path)

    assert (
        main(
            [
                "enrol",
                "--image",
                str(tag_path),
                "--image",
                str(tag_path),
                "--image",
                str(tag_path),
                "--product-id",
                "product-test-1",
                "--vendor-id",
                "vendor-abc",
                "--output-dir",
                str(bundle_dir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["verify", "--bundle", str(bundle_dir / "enrolment.json"), "--image", str(washed_out_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["structural_verdict"] == "pass"
    assert report["color_verdict"] == "fail"
    assert report["verdict"] == "pass"
