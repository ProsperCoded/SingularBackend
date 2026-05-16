from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Optional
from pydantic import BaseModel

from services.engine.pipeline import DEFAULT_ENROLMENT_SCAN_COUNT, EnrolResult, GenerateResult, ImageSource


class VerificationResult(BaseModel):
    """
    The exact shape of the data The Architect must return after analyzing a scan.
    """

    score: float
    verdict: str  # Must be one of: "AUTHENTIC", "SUSPICIOUS", "FAKE"
    details: dict[str, object] | None = None


class PUFEngineInterface(ABC):
    """
    The formal contract between The Backbone (API) and The Architect (Core Engine).
    Any class implementing this interface must provide concrete logic for these methods.
    """

    @abstractmethod
    async def generate_tag(
        self, product_id: str, vendor_id: Optional[str] = None
    ) -> GenerateResult:
        """
        Triggers the generation pipeline to create a printable PUF tag.

        Args:
            product_id: The product ID encoded in the QR payload.
            vendor_id: The optional vendor assigned to this tag.

        Returns:
            A GenerateResult containing the QR PNG bytes.
        """
        pass

    @abstractmethod
    async def enrol_tag(
        self,
        image_source: ImageSource | Sequence[ImageSource],
        product_id: str,
        vendor_id: Optional[str] = None,
        required_scan_count: int = DEFAULT_ENROLMENT_SCAN_COUNT,
    ) -> EnrolResult:
        """
        Triggers the enrolment pipeline for a single tag.

        Args:
            image_source: One or more images captured from the printed tag.
            product_id: The product ID encoded in the QR payload.
            vendor_id: The optional vendor assigned to this tag.
            required_scan_count: The minimum number of scans used for enrolment.

        Returns:
            An EnrolResult containing the averaged enrolment bundle.
        """
        pass

    @abstractmethod
    async def verify_tag(
        self,
        image_bytes: bytes,
        product_id: str,
        enrolment_bundle: Mapping[str, object] | None = None,
    ) -> VerificationResult:
        """
        Runs the verification pipeline on a captured image.

        Args:
            image_bytes: The raw bytes of the 1200x1200px JPEG captured by the frontend.
            product_id: The decoded product ID extracted from the QR payload.
            enrolment_bundle: The persisted bundle for this tag, if available.

        Returns:
            A VerificationResult containing the composite verification score and the final backend verdict.
        """
        pass
