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
            return VerificationResult(
                score=0.0,
                verdict="FAKE",
                details={
                    "composite_score": 0.0,
                    "score_source": "rule_based",
                    "lbp_similarity": 0.0,
                    "sharpness_score": 0.0,
                    "sharpness_ratio": 0.0,
                    "vector_similarity": 0.0,
                    "mean_vector_similarity": 0.0,
                    "enrolled_halftone_mean": 0.0,
                    "enrolled_halftone_max": 0.0,
                    "query_halftone_mean": 0.0,
                    "query_halftone_max": 0.0,
                    "primary_phash_distance": None,
                    "support_phash_distance": None,
                    "canvas_phash_distance": None,
                    "color_distance": None,
                    "structural_verdict": "fail",
                    "color_verdict": "fail",
                    "verdict_reasons": [],
                    "thresholds": None,
                },
            )

        summary = await run_in_threadpool(verify_enrolment_bundle, enrolment_bundle, image_bytes)
        return VerificationResult(
            score=summary.composite_score,
            verdict=map_engine_verdict_to_backend(summary.verdict),
            details={
                "composite_score": summary.composite_score,
                "score_source": summary.score_source,
                "lbp_similarity": summary.lbp_score,
                "sharpness_score": summary.sharpness_score,
                "sharpness_ratio": summary.sharpness_ratio,
                "vector_similarity": summary.vector_score,
                "mean_vector_similarity": summary.mean_vector_score,
                "enrolled_halftone_mean": summary.enrolled_halftone_mean,
                "enrolled_halftone_max": summary.enrolled_halftone_max,
                "query_halftone_mean": summary.query_halftone_mean,
                "query_halftone_max": summary.query_halftone_max,
                "primary_phash_distance": summary.primary_phash_distance,
                "support_phash_distance": summary.support_phash_distance,
                "canvas_phash_distance": summary.canvas_phash_distance,
                "color_distance": round(summary.color_distance, 4),
                "structural_verdict": summary.structural_verdict,
                "color_verdict": summary.color_verdict,
                "verdict_reasons": summary.verdict_reasons,
                "thresholds": summary.thresholds,
            },
        )


engine = PrintPUFEngineAdapter()
