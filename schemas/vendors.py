from schemas.scans import ScanStats
from pydantic import BaseModel, Field


class VendorDashboardResponse(BaseModel):
    vendor_id: str
    trust_score: float
    badge_tier: str
    score_trend: str = Field(..., description="e.g., 'up', 'down', 'stable'")
    stats: ScanStats


class VendorTrustInfo(BaseModel):
    vendor_id: str
    trust_score: float = Field(..., description="Score out of 100")
    badge_tier: str = Field(..., description="Bronze, Silver, or Gold")


class ProductDetails(BaseModel):
    product_name: str
    manufacturer: str
    product_type: str
