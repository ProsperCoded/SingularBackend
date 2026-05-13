from sqlmodel import SQLModel, Field
from datetime import datetime, timezone


class Product(SQLModel, table=True):
    """
    Lightweight mapping from an individual product tag to its parent batch.
    The Architect populates this during enrollment (inside generate_batch).
    The Backbone uses it to resolve product_id to vendor, product_type, and brand
    during verification without dealing with SQL JOINs for performance gain.
    """

    id: str = Field(primary_key=True, description="The product_id encoded in the QR")
    batch_id: str = Field(index=True, description="FK to Batch.id")
    product_type: str = Field(description="Copied from Batch for quick access")
    vendor_id: str | None = Field(default=None, description="Copied from Batch")
    brand_id: str = Field(description="Copied from Batch for quick access")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
