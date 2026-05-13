from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.database import get_db_session
from services.dummy_engine import engine
from services.trust import compute_trust_score

from models.product import Product
from models.scan_event import ScanEvent
from models.user import User

from schemas.scan import ScanResultResponse, ProductDetails, VendorLookupResponse
from schemas.vendor import VendorTrustInfo, ScanStats

router = APIRouter(prefix="/verify", tags=["Verification"])


@router.post("/product", response_model=ScanResultResponse)
async def verify_product(
    image: UploadFile = File(..., description="1200×1200px JPEG of the physical tag"),
    product_id: str = Form(..., description="Decoded product ID from the QR payload"),
    device_hash: str | None = Form(
        default=None, description="Browser fingerprint for anonymous tracking"
    ),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Full PUF verification pipeline for product-tag scans.
    Public endpoint, no authentication required (consumer scans are anonymous).
    """

    # Read the uploaded image
    image_bytes = await image.read()

    # Call the engine for verification
    result = await engine.verify_tag(image_bytes, product_id)

    # Resolve product details from the Product table
    product_record = await session.get(Product, product_id)

    product_details = None
    vendor_trust = None
    vendor_id = None

    if product_record:
        vendor_id = product_record.vendor_id
        product_details = ProductDetails(
            product_name=product_id,
            manufacturer=product_record.brand_id,
            product_type=product_record.product_type,
        )

        # If vendor exists, compute trust score
        if vendor_id:
            trust_score, badge_tier, _ = await compute_trust_score(
                session, vendor_id
            )
            vendor_trust = VendorTrustInfo(
                vendor_id=vendor_id,
                trust_score=trust_score,
                badge_tier=badge_tier,
            )

    # Generate report URL for FAKE verdicts
    report_url = None
    if result.verdict == "FAKE":
        report_url = (
            f"https://wa.me/?text=FAKE%20product%20detected%20"
            f"(ID%3A%20{product_id}).%20Report%20to%20NAFDAC."
        )

    # Log the scan event
    scan_event = ScanEvent(
        product_id=product_id,
        vendor_id=vendor_id,
        verdict=result.verdict,
        score=result.score,
        device_hash=device_hash,
    )
    session.add(scan_event)
    await session.commit()

    # Return the result
    return ScanResultResponse(
        verdict=result.verdict,
        score=result.score,
        product=product_details,
        vendor=vendor_trust,
        report_url=report_url,
    )


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
