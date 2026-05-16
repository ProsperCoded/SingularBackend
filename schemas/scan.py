from typing import Optional
from pydantic import Field, BaseModel

from schemas.vendor import VendorTrustInfo, ScanStats


class ProductDetails(BaseModel):
    product_name: str
    manufacturer: str
    product_type: str


class VerificationDetailsResponse(BaseModel):
    composite_score: float = Field(..., description="Fused verification score out of 100")
    score_source: str = Field(..., description="'rule_based' or 'calibrated_model' for the active scoring path")
    lbp_similarity: float = Field(..., description="Cosine similarity of the enrolled and live LBP texture vectors from 0 to 1")
    sharpness_score: float = Field(..., description="Variance of the Laplacian on the live raw texture crop")
    sharpness_ratio: float = Field(..., description="Live sharpness divided by the enrolled sharpness baseline")
    vector_similarity: float = Field(..., description="Cosine similarity of the learned feature vector from 0 to 1")
    mean_vector_similarity: float = Field(..., description="Cosine similarity against the averaged enrolled vector from 0 to 1")
    enrolled_halftone_mean: float = Field(..., description="Mean enrolled halftone periodicity baseline across reference patches")
    enrolled_halftone_max: float = Field(..., description="Maximum enrolled halftone periodicity baseline across reference patches")
    query_halftone_mean: float = Field(..., description="Mean live halftone periodicity score across reference patches")
    query_halftone_max: float = Field(..., description="Maximum live halftone periodicity score across reference patches")
    primary_phash_distance: int | None = Field(None, description="Perceptual hash distance on the full tag content region")
    support_phash_distance: int | None = Field(None, description="Perceptual hash distance on the support fragment strip")
    canvas_phash_distance: int | None = Field(None, description="Perceptual hash distance on the full aligned canvas")
    color_distance: float | None = Field(None, description="Euclidean distance between enrolled and live color signatures")
    structural_verdict: str = Field(..., description="'pass', 'suspicious', or 'fail' for structure-only checks")
    color_verdict: str = Field(..., description="'pass', 'suspicious', or 'fail' for color-only checks")
    verdict_reasons: list[str] = Field(default_factory=list, description="Structured diagnostic reasons affecting the final verdict")
    thresholds: dict[str, float | int | str] | None = Field(
        None,
        description="Thresholds used during verification for debugging and UI explanation",
    )


class ScanResultResponse(BaseModel):
    product_id: str
    verdict: str = Field(..., description="'AUTHENTIC', 'SUSPICIOUS', or 'FAKE'")
    score: float = Field(..., description="Composite verification score out of 100")
    verification: VerificationDetailsResponse
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
