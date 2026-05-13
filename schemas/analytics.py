from pydantic import Field, BaseModel

from schemas.vendor import VendorPerformance


class BrandAnalyticsResponse(BaseModel):
    total_scans: int
    authentic_rate: float = Field(..., description="Percentage of authentic scans")
    fake_attempts: int
    vendor_management: list[VendorPerformance] = Field(
        ..., description="Per-vendor authentic/fake ratio"
    )
