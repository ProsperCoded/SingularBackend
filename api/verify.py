from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.database import get_db_session
from services.trust import compute_trust_score

from models.user import User

from schemas.scan import VendorLookupResponse
from schemas.vendor import ScanStats

router = APIRouter(prefix="/verify", tags=["Verification"])


@router.get("/vendor/{vendor_id}", response_model=VendorLookupResponse)
async def verify_vendor(
    vendor_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Vendor trust score lookup for vendor-QR scans.
    Public endpoint, no auth required.
    """

    # Look up the vendor's user record
    statement = select(User).where(User.vendor_id == vendor_id)
    result = await session.exec(statement)
    vendor = result.first()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor '{vendor_id}' not found.",
        )

    # Compute trust score and stats
    trust_score, badge_tier, stats = await compute_trust_score(session, vendor_id)

    return VendorLookupResponse(
        vendor_id=vendor_id,
        trust_score=trust_score,
        badge_tier=badge_tier,
        stats=ScanStats(**stats),
    )
