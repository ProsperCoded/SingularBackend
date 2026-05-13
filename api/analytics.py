from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, func, col
from sqlmodel.ext.asyncio.session import AsyncSession

from core.auth import get_current_user
from core.database import get_db_session

from models.user import User, UserRole
from models.product import Product
from models.scan_event import ScanEvent

from schemas.analytics import BrandAnalyticsResponse
from schemas.vendor import VendorPerformance

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/brand", response_model=BrandAnalyticsResponse)
async def get_brand_analytics(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Analytics overview for the authenticated brand.
    Aggregates scan data across all products belonging to this brand.
    """

    if current_user.role != UserRole.BRAND:
        raise HTTPException(status_code=403, detail="Only Brands can view analytics.")

    # Get all product IDs belonging to this brand
    product_ids_stmt = select(Product.id).where(Product.brand_id == current_user.id)
    product_ids_result = await session.exec(product_ids_stmt)
    product_ids = product_ids_result.all()

    if not product_ids:
        return BrandAnalyticsResponse(
            total_scans=0,
            authentic_rate=0.0,
            fake_attempts=0,
            vendor_management=[],
        )

    # Aggregate scan events by verdict for this brand's products
    scan_stats_stmt = (
        select(ScanEvent.verdict, func.count(ScanEvent.id))
        .where(col(ScanEvent.product_id).in_(product_ids))
        .group_by(ScanEvent.verdict)
    )
    scan_stats_result = await session.exec(scan_stats_stmt)
    counts = {row[0]: row[1] for row in scan_stats_result.all()}

    authentic = counts.get("AUTHENTIC", 0)
    fake = counts.get("FAKE", 0)
    suspicious = counts.get("SUSPICIOUS", 0)
    total = authentic + fake + suspicious

    authentic_rate = round((authentic / total) * 100, 2) if total > 0 else 0.0

    # Per-vendor breakdown
    vendor_stats_stmt = (
        select(
            ScanEvent.vendor_id,
            ScanEvent.verdict,
            func.count(ScanEvent.id),
        )
        .where(
            col(ScanEvent.product_id).in_(product_ids),
            ScanEvent.vendor_id.isnot(None),
        )
        .group_by(ScanEvent.vendor_id, ScanEvent.verdict)
    )
    vendor_stats_result = await session.exec(vendor_stats_stmt)

    # Build per-vendor totals: {vendor_id: {verdict: count}}
    vendor_data: dict[str, dict[str, int]] = {}
    for vendor_id, verdict, count in vendor_stats_result.all():
        if vendor_id not in vendor_data:
            vendor_data[vendor_id] = {}
        vendor_data[vendor_id][verdict] = count

    vendor_management = []
    for vendor_id, verdicts in vendor_data.items():
        v_authentic = verdicts.get("AUTHENTIC", 0)
        v_total = sum(verdicts.values())
        ratio = round(v_authentic / v_total, 4) if v_total > 0 else 0.0
        vendor_management.append(
            VendorPerformance(vendor_id=vendor_id, authentic_ratio=ratio)
        )

    return BrandAnalyticsResponse(
        total_scans=total,
        authentic_rate=authentic_rate,
        fake_attempts=fake,
        vendor_management=vendor_management,
    )
