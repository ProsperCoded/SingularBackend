from typing import Optional
from pydantic import Field, BaseModel

from schemas.vendor import VendorTrustInfo, ScanStats


class ProductDetails(BaseModel):
    product_name: str
    manufacturer: str
    product_type: str


class ScanResultResponse(BaseModel):
    product_id: str
    verdict: str = Field(..., description="'AUTHENTIC', 'SUSPICIOUS', or 'FAKE'")
    score: float = Field(..., description="Cosine similarity score from the engine")
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
