from __future__ import annotations

import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.auth import get_current_user
from core.database import get_db_session
from core.payment import verify_squad_transaction
from models.product import Product
from models.scan_event import ScanEvent
from models.user import User, UserRole
from schemas.scan import ProductDetails, ScanResultResponse
from schemas.tags import TagEnrolResponse, TagGenerateResponse, TagItemResponse, TagListResponse
from schemas.vendor import VendorTrustInfo
from services.engine.bundle import serialize_enrolment_bundle
from services.engine_adapter import engine
from services.trust import compute_trust_score


router = APIRouter(prefix="/tags", tags=["Tags"])

COST_PER_TAG_KOBO = 150
REQUIRED_ENROLMENT_SCANS = 3


def _encode_png_bytes(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


@router.post("/generate", response_model=TagGenerateResponse)
async def generate_tag(
    transaction_ref: str = Form(...),
    product_type: str = Form(...),
    vendor_id: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if current_user.role != UserRole.BRAND:
        raise HTTPException(status_code=403, detail="Only Brands can generate tags.")

    existing_tag_statement = select(Product).where(Product.transaction_ref == transaction_ref)
    existing_tag = (await session.exec(existing_tag_statement)).first()
    if existing_tag:
        raise HTTPException(
            status_code=409,
            detail="This transaction reference has already been used to generate a tag.",
        )

    await verify_squad_transaction(transaction_ref, COST_PER_TAG_KOBO)

    product_id = uuid.uuid4().hex
    generated_tag = await engine.generate_tag(product_id=product_id, vendor_id=vendor_id)

    product = Product(
        id=product_id,
        brand_id=current_user.id,
        vendor_id=vendor_id,
        product_type=product_type,
        transaction_ref=transaction_ref,
        status="generated",
        qr_png_b64=_encode_png_bytes(generated_tag.qr_png_bytes),
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)

    return TagGenerateResponse(
        product_id=product.id,
        brand_id=product.brand_id,
        vendor_id=product.vendor_id,
        product_type=product.product_type,
        transaction_ref=product.transaction_ref,
        qr_png_b64=product.qr_png_b64 or "",
        status=product.status,
        created_at=product.created_at,
    )


@router.post("/enrol", response_model=TagEnrolResponse)
async def enrol_tag(
    product_id: str = Form(...),
    images: list[UploadFile] = File(..., description="Exactly three enrolment scans of the same tag"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if current_user.role != UserRole.BRAND:
        raise HTTPException(status_code=403, detail="Only Brands can enrol tags.")

    if len(images) != REQUIRED_ENROLMENT_SCANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exactly {REQUIRED_ENROLMENT_SCANS} enrolment scans are required.",
        )

    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Tag not found.")
    if product.brand_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this tag.")

    image_bytes = [await image.read() for image in images]
    enrolment_result = await engine.enrol_tag(
        image_source=image_bytes,
        product_id=product.id,
        vendor_id=product.vendor_id,
        required_scan_count=REQUIRED_ENROLMENT_SCANS,
    )

    product.enrolment_bundle = serialize_enrolment_bundle(enrolment_result, vendor_id=product.vendor_id)
    product.qr_png_b64 = _encode_png_bytes(enrolment_result.updated_qr_png_bytes)
    product.enrolment_scan_count = enrolment_result.scan_count
    product.status = "enrolled"
    product.enrolled_at = datetime.utcnow()
    product.updated_at = datetime.utcnow()
    session.add(product)
    await session.commit()
    await session.refresh(product)

    return TagEnrolResponse(
        product_id=product.id,
        brand_id=product.brand_id,
        vendor_id=product.vendor_id,
        product_type=product.product_type,
        status=product.status,
        enrolment_scan_count=product.enrolment_scan_count,
        qr_png_b64=product.qr_png_b64 or "",
        enrolled_at=product.enrolled_at or product.created_at,
        updated_at=product.updated_at,
    )


@router.get("/list", response_model=TagListResponse)
async def list_tags(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if current_user.role != UserRole.BRAND:
        raise HTTPException(status_code=403, detail="Only Brands can view tags.")

    statement = select(Product).where(Product.brand_id == current_user.id).order_by(Product.created_at.desc())
    results = await session.exec(statement)
    products = results.all()

    return TagListResponse(
        tags=[
            TagItemResponse(
                product_id=product.id,
                brand_id=product.brand_id,
                vendor_id=product.vendor_id,
                product_type=product.product_type,
                status=product.status,
                transaction_ref=product.transaction_ref,
                enrolment_scan_count=product.enrolment_scan_count,
                created_at=product.created_at,
                enrolled_at=product.enrolled_at,
            )
            for product in products
        ]
    )


@router.post("/verify", response_model=ScanResultResponse)
async def verify_tag(
    image: UploadFile = File(..., description="1200×1200px JPEG of the physical tag"),
    product_id: str = Form(..., description="Decoded product ID from the QR payload"),
    device_hash: str | None = Form(default=None, description="Browser fingerprint for anonymous tracking"),
    session: AsyncSession = Depends(get_db_session),
):
    image_bytes = await image.read()
    product_record = await session.get(Product, product_id)

    if product_record and product_record.enrolment_bundle is not None:
        result = await engine.verify_tag(
            image_bytes=image_bytes,
            product_id=product_id,
            enrolment_bundle=product_record.enrolment_bundle,
        )
    else:
        result = await engine.verify_tag(image_bytes=image_bytes, product_id=product_id, enrolment_bundle=None)

    product_details = None
    vendor_trust = None
    vendor_id = None

    if product_record:
        vendor_id = product_record.vendor_id
        product_details = ProductDetails(
            product_name=product_record.id,
            manufacturer=product_record.brand_id,
            product_type=product_record.product_type,
        )

        if vendor_id:
            trust_score, badge_tier, _ = await compute_trust_score(session, vendor_id)
            vendor_trust = VendorTrustInfo(
                vendor_id=vendor_id,
                trust_score=trust_score,
                badge_tier=badge_tier,
            )

    report_url = None
    if result.verdict == "FAKE":
        report_url = (
            f"https://wa.me/?text=FAKE%20product%20detected%20"
            f"(ID%3A%20{product_id}).%20Report%20to%20NAFDAC."
        )

    scan_event = ScanEvent(
        product_id=product_id,
        vendor_id=vendor_id,
        verdict=result.verdict,
        score=result.score,
        device_hash=device_hash,
    )
    session.add(scan_event)
    await session.commit()

    return ScanResultResponse(
        verdict=result.verdict,
        score=result.score,
        product=product_details,
        vendor=vendor_trust,
        report_url=report_url,
    )

