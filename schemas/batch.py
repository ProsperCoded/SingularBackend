from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class BatchGenerateRequest(BaseModel):
    transaction_ref: str = Field(
        ...,
        description="The unique transaction reference returned by the Squad payment widget.",
    )
    quantity: int = Field(
        ..., gt=0, description="The number of tags to generate. Must be greater than 0."
    )
    product_type: str = Field(
        ...,
        description="The category or name of the product (e.g., 'Sneakers', 'Handbag').",
    )
    vendor_id: Optional[str] = Field(
        default=None,
        description="The optional ID of the vendor this batch is assigned to.",
    )


class BatchResponse(BaseModel):
    id: str
    brand_id: str
    vendor_id: Optional[str]
    product_type: str
    quantity: int
    transaction_ref: str
    download_urls: List[str]
    created_at: datetime

    class Config:
        # This tells Pydantic to seamlessly read the data out of your SQLModel database row
        from_attributes = True
