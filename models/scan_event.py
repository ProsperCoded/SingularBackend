from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid


class ScanEvent(SQLModel, table=True):
    """
    Append-only log of every consumer scan for analytics, trust score computation,
    and brand dashboard reporting. Consumer scans are anonymous —
    no user account is linked, and verification never deletes the underlying tag.
    """

    __tablename__ = "scanevent"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    product_id: str = Field(index=True, description="QR-decoded product ID")
    vendor_id: str | None = Field(
        default=None, index=True, description="Resolved from Product record"
    )
    verdict: str = Field(description="AUTHENTIC, SUSPICIOUS, or FAKE")
    score: float = Field(description="Composite verification score from the engine")
    device_hash: str | None = Field(
        default=None, description="Browser fingerprint for anonymous tracking"
    )
    scanned_at: datetime = Field(default_factory=datetime.utcnow)
