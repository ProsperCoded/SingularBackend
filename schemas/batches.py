from datetime import datetime
from typing import Optional
from pydantic import Field, BaseModel


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
