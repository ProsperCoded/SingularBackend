from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.engine_contract import VerificationResult
from services.engine.bundle import map_engine_verdict_to_backend
from services.engine.pipeline import GenerateResult
from services.engine_adapter import PrintPUFEngineAdapter


def test_engine_verdict_mapping_to_backend_vocabulary() -> None:
    assert map_engine_verdict_to_backend("pass") == "AUTHENTIC"
    assert map_engine_verdict_to_backend("suspicious") == "SUSPICIOUS"
    assert map_engine_verdict_to_backend("fail") == "FAKE"


def test_adapter_generate_and_enrol_use_pipeline_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = PrintPUFEngineAdapter()

    def _fake_generate_qr_only(product_id: str, vendor_id: str | None = None):
        return GenerateResult(product_id=product_id, qr_png_bytes=b"generated")

    def _fake_enrol(image_source, product_id: str, vendor_id: str | None, private_key_pem, required_scan_count: int):
        return SimpleNamespace(scan_count=required_scan_count, updated_qr_png_bytes=b"updated")

    monkeypatch.setattr("services.engine_adapter.generate_qr_only", _fake_generate_qr_only)
    monkeypatch.setattr("services.engine_adapter.enrol", _fake_enrol)

    generated = asyncio.run(adapter.generate_tag("product-1", "vendor-9"))
    enrolled = asyncio.run(adapter.enrol_tag([b"scan-1", b"scan-2", b"scan-3"], "product-1", "vendor-9"))

    assert generated.product_id == "product-1"
    assert generated.qr_png_bytes == b"generated"
    assert enrolled.scan_count == 3
    assert enrolled.updated_qr_png_bytes == b"updated"


def test_adapter_verify_maps_engine_verdict_to_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = PrintPUFEngineAdapter()

    def _fake_verify_enrolment_bundle(bundle_source, image_source):
        return SimpleNamespace(verdict="pass", vector_score=0.97)

    monkeypatch.setattr("services.engine_adapter.verify_enrolment_bundle", _fake_verify_enrolment_bundle)

    result = asyncio.run(adapter.verify_tag(b"image-bytes", "product-1", {"product_id": "product-1"}))

    assert isinstance(result, VerificationResult)
    assert result.score == 0.97
    assert result.verdict == "AUTHENTIC"

