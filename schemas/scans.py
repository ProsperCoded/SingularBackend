from schemas.vendors import VendorTrustInfo
from schemas.vendors import ProductDetails
from typing import Optional
from pydantic import Field
from pydantic import BaseModel


class ScanStats(BaseModel):
    total_scans: int
    authentic_scans: int
    fake_attempts: int
    suspicious_scans: int


class ScanResultResponse(BaseModel):
    verdict: str = Field(..., description="'AUTHENTIC', 'SUSPICIOUS', or 'FAKE'")
    score: float = Field(..., description="Cosine similarity score from the engine")
    product: Optional[ProductDetails] = None
    vendor: Optional[VendorTrustInfo] = None
    report_url: Optional[str] = Field(
        None, description="Pre-filled WhatsApp/NAFDAC URL for FAKE results"
    )
