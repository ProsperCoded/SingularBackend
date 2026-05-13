import io
from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel


class VerificationResult(BaseModel):
    """
    The exact shape of the data The Architect must return after analyzing a scan.
    """

    score: float
    verdict: str  # Must be one of: "AUTHENTIC", "SUSPICIOUS", "FAKE"


class PUFEngineInterface(ABC):
    """
    The formal contract between The Backbone (API) and The Architect (Core Engine).
    Any class implementing this interface must provide concrete logic for these methods.
    """

    @abstractmethod
    async def generate_batch(
        self, quantity: int, product_type: str, vendor_id: Optional[str] = None
    ) -> List[io.BytesIO]:
        """
        Triggers the enrolment pipeline to generate a batch of PUF tags.

        Args:
            quantity: The number of unique tags to generate.
            product_type: The category of the product (e.g., 'Sneakers').
            vendor_id: The optional vendor assigned to this batch.

        Returns:
            A list of in-memory byte streams representing the generated A4 pages
            (PDFs or SVGs), ready for the Backbone to upload to DigitalOcean Spaces.
        """
        pass

    @abstractmethod
    async def verify_tag(
        self, image_bytes: bytes, product_id: str
    ) -> VerificationResult:
        """
        Runs the verification pipeline on a captured image.
        This method is responsible for running pHash, LBP, SIFT, and MobileNetV2,
        and querying the pgvector database.

        Args:
            image_bytes: The raw bytes of the 1200x1200px JPEG captured by the frontend.
            product_id: The decoded product ID extracted from the QR payload.

        Returns:
            A VerificationResult containing the cosine similarity score and the final verdict.
        """
        pass
