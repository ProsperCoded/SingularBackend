from datetime import datetime
from typing import Optional
from pydantic import Field, BaseModel


class GenerateVendorIdResponse(BaseModel):
    generated_id: str


class CheckVendorIdResponse(BaseModel):
    available: bool


class ConfirmVendorIdResponse(BaseModel):
    message: str
    vendor_id: str


class BatchItemResponse(BaseModel):
    batch_id: str
    date_generated: datetime
    quantity: int
    product_type: str
    vendor_id: Optional[str] = Field(None, description="Assigned vendor, if any")
    download_url: str = Field(..., description="DigitalOcean Spaces URL for the ZIP")
    expires_at: datetime = Field(..., description="30 days from generation date")
    is_active: bool = Field(..., description="False if 30 days have passed")


class BrandBatchesResponse(BaseModel):
    batches: list[BatchItemResponse]


class ScanStats(BaseModel):
    total_scans: int
    authentic_scans: int
    fake_attempts: int
    suspicious_scans: int


class VendorTrustInfo(BaseModel):
    vendor_id: str
    trust_score: float = Field(..., description="Score out of 100")
    badge_tier: str = Field(..., description="Bronze, Silver, or Gold")


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


class VendorDashboardResponse(BaseModel):
    vendor_id: str
    trust_score: float
    badge_tier: str
    score_trend: str = Field(..., description="e.g., 'up', 'down', 'stable'")
    stats: ScanStats


class ConfirmVendorId(BaseModel):
    vendor_id: str


class VendorPerformance(BaseModel):
    vendor_id: str
    authentic_ratio: float


class BrandAnalyticsResponse(BaseModel):
    total_scans: int
    authentic_rate: float = Field(..., description="Percentage of authentic scans")
    fake_attempts: int
    active_states: int = Field(..., description="Number of unique states with scans")
    vendor_management: list[VendorPerformance] = Field(
        ..., description="Per-vendor authentic/fake ratio"
    )
