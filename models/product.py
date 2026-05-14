from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    """
    Canonical record for an individual tag.
    The backbone stores the QR asset and enrolment bundle here so verification
    can stay stateless at request time.
    """

    id: str = Field(primary_key=True, description="The product_id encoded in the QR")
    brand_id: str = Field(index=True, description="Brand that owns this tag")
    vendor_id: str | None = Field(default=None, index=True, description="Optional vendor assignment")
    product_type: str = Field(index=True, description="Tag/product category")
    transaction_ref: str = Field(unique=True, index=True, description="Squad transaction reference used to generate the tag")
    status: str = Field(default="generated", index=True, description="generated, enrolled, or archived")
    qr_png_b64: str | None = Field(default=None, description="Base64-encoded QR PNG asset")
    enrolment_bundle: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Serialized enrolment bundle used for verification",
    )
    enrolment_scan_count: int = Field(default=0)
    enrolled_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
