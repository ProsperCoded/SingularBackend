from typing import Optional
from pydantic import Field, BaseModel

from schemas.vendor import VendorTrustInfo, ScanStats


class ProductDetails(BaseModel):
    product_name: str
    manufacturer: str
    product_type: str


class VerificationDetails(BaseModel):
    composite_score: float
    score_source: str
    lbp_similarity: Optional[float] = None
    vector_similarity: Optional[float] = None
    mean_vector_similarity: Optional[float] = None
    enrolled_halftone_mean: Optional[float] = None
    enrolled_halftone_max: Optional[float] = None
    query_halftone_mean: Optional[float] = None
    query_halftone_max: Optional[float] = None
    primary_phash_distance: Optional[int] = None
    support_phash_distance: Optional[int] = None
    canvas_phash_distance: Optional[int] = None
    color_distance: Optional[float] = None
    structural_verdict: Optional[str] = None
    color_verdict: Optional[str] = None
    verdict_reasons: list[str] = []
    thresholds: Optional[dict] = None


class ScanResultResponse(BaseModel):
    product_id: str
    verdict: str = Field(..., description="'AUTHENTIC', 'SUSPICIOUS', or 'FAKE'")
    score: float = Field(..., description="Cosine similarity score from the engine")
    verification: Optional[VerificationDetails] = None
    product: Optional[ProductDetails] = None
    vendor: Optional[VendorTrustInfo] = None
    report_url: Optional[str] = Field(
        None, description="Pre-filled WhatsApp/NAFDAC URL for FAKE results"
    )


class VendorLookupResponse(BaseModel):
    """Response for vendor-QR scans: no image processing, just trust info."""

    vendor_id: str
    trust_score: float = Field(..., description="Score out of 100")
    badge_tier: str = Field(..., description="Bronze, Silver, or Gold")
    stats: ScanStats
