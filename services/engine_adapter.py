from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi.concurrency import run_in_threadpool

from core.engine_contract import PUFEngineInterface, VerificationResult
from services.engine.bundle import map_engine_verdict_to_backend, verify_enrolment_bundle
from services.engine.pipeline import DEFAULT_ENROLMENT_SCAN_COUNT, EnrolResult, GenerateResult, ImageSource, enrol, generate_qr_only


class PrintPUFEngineAdapter(PUFEngineInterface):
    async def generate_tag(self, product_id: str, vendor_id: str | None = None) -> GenerateResult:
        return await run_in_threadpool(generate_qr_only, product_id, vendor_id)

    async def enrol_tag(
        self,
        image_source: ImageSource | Sequence[ImageSource],
        product_id: str,
        vendor_id: str | None = None,
        required_scan_count: int = DEFAULT_ENROLMENT_SCAN_COUNT,
    ) -> EnrolResult:
        return await run_in_threadpool(enrol, image_source, product_id, vendor_id, None, required_scan_count)

    async def verify_tag(
        self,
        image_bytes: bytes,
        product_id: str,
        enrolment_bundle: Mapping[str, object] | None = None,
    ) -> VerificationResult:
        if enrolment_bundle is None:
            return VerificationResult(score=0.0, verdict="FAKE")

        summary = await run_in_threadpool(verify_enrolment_bundle, enrolment_bundle, image_bytes)
        return VerificationResult(
            score=summary.vector_score,
            verdict=map_engine_verdict_to_backend(summary.verdict),
        )


engine = PrintPUFEngineAdapter()

