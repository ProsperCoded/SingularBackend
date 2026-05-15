from pydantic import Field, BaseModel


class GenerateVendorIdResponse(BaseModel):
    generated_id: str


class CheckVendorIdResponse(BaseModel):
    available: bool


class ConfirmVendorIdResponse(BaseModel):
    message: str
    vendor_id: str


class ConfirmVendorId(BaseModel):
    vendor_id: str


class VendorTrustInfo(BaseModel):
    vendor_id: str
    trust_score: float = Field(..., description="Score out of 100")
    badge_tier: str = Field(..., description="Bronze, Silver, or Gold")


class ScanStats(BaseModel):
    total_scans: int
    authentic_scans: int
    fake_attempts: int
    suspicious_scans: int


class VendorDashboardResponse(BaseModel):
    vendor_id: str
    trust_score: float
    badge_tier: str
    score_trend: str = Field(..., description="e.g., 'up', 'down', 'stable'")
    stats: ScanStats


class VendorPerformance(BaseModel):
    vendor_id: str
    authentic_ratio: float


class VendorDirectoryItem(BaseModel):
    vendor_id: str
    full_name: str
    trust_score: float
    badge_tier: str
    total_scans: int


class VendorDirectoryResponse(BaseModel):
    vendors: list[VendorDirectoryItem]
