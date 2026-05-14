from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TagGenerateResponse(BaseModel):
    product_id: str
    brand_id: str
    vendor_id: Optional[str]
    product_type: str
    transaction_ref: str
    qr_png_b64: str = Field(..., description="Base64-encoded QR PNG asset")
    status: str
    created_at: datetime


class TagEnrolResponse(BaseModel):
    product_id: str
    brand_id: str
    vendor_id: Optional[str]
    product_type: str
    status: str
    enrolment_scan_count: int
    qr_png_b64: str = Field(..., description="Base64-encoded updated QR PNG asset")
    enrolled_at: datetime
    updated_at: datetime


class TagItemResponse(BaseModel):
    product_id: str
    brand_id: str
    vendor_id: Optional[str]
    product_type: str
    status: str
    transaction_ref: str
    enrolment_scan_count: int
    created_at: datetime
    enrolled_at: Optional[datetime]


class TagListResponse(BaseModel):
    tags: list[TagItemResponse]

