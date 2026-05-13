from typing import Optional
from pydantic import Field, BaseModel

from schemas.vendor import VendorTrustInfo


class ProductDetails(BaseModel):
    product_name: str
    manufacturer: str
    product_type: str


class ScanResultResponse(BaseModel):
    verdict: str = Field(..., description="'AUTHENTIC', 'SUSPICIOUS', or 'FAKE'")
    score: float = Field(..., description="Cosine similarity score from the engine")
    product: Optional[ProductDetails] = None
    vendor: Optional[VendorTrustInfo] = None
    report_url: Optional[str] = Field(
        None, description="Pre-filled WhatsApp/NAFDAC URL for FAKE results"
    )
