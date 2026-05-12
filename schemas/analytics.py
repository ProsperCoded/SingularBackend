from pydantic import BaseModel, Field


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
