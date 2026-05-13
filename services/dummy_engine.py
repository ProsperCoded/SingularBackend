import io
from core.engine_contract import PUFEngineInterface, VerificationResult
from typing import List


class DummyArchitectEngine(PUFEngineInterface):
    async def generate_batch(
        self, quantity: int, product_type: str, vendor_id: str = None
    ) -> List[io.BytesIO]:
        # Pretend we generated 2 pages of PDFs
        return [io.BytesIO(b"fake pdf page 1"), io.BytesIO(b"fake pdf page 2")]

    async def verify_tag(
        self, image_bytes: bytes, product_id: str
    ) -> VerificationResult:
        # Pretend the image was perfectly authentic
        return VerificationResult(score=0.98, verdict="AUTHENTIC")


# Instantiate it to use in your API routes today
engine = DummyArchitectEngine()
