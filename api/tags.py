from __future__ import annotations

import base64
import uuid
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import cbor2

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.auth import get_current_user
from core.config import settings
from core.database import get_db_session
from core.payment import verify_squad_transaction
from core.payment import initiate_squad_transaction
from core.spaces import download_qr_png, encode_png_bytes, upload_qr_png
from models.product import Product
from models.scan_event import ScanEvent
from models.user import User, UserRole

from schemas.scan import ProductDetails, ScanResultResponse
from schemas.tags import (
    TagEnrolResponse,
    TagGenerateResponse,
    TagItemResponse,
    TagListResponse,
    TagPaymentInitiateRequest,
    TagPaymentInitiateResponse,
)
from schemas.vendor import VendorTrustInfo
from services.engine.bundle import serialize_enrolment_bundle
from services.engine_adapter import engine
from services.trust import compute_trust_score


router = APIRouter(prefix="/tags", tags=["Tags"])

COST_PER_TAG_KOBO = 15000
REQUIRED_ENROLMENT_SCANS = 3


def _encode_png_bytes(png_bytes: bytes) -> str:
    return encode_png_bytes(png_bytes)


def _persist_qr_png(product_id: str, png_bytes: bytes) -> None:
    try:
        upload_qr_png(product_id, png_bytes)
    except Exception as exc:
        print(f"[spaces] Failed to upload QR asset for {product_id}: {exc}")


def _resolve_qr_png_b64(product_id: str, cached_b64: str | None) -> str:
    try:
        stored_png = download_qr_png(product_id)
    except Exception as exc:
        print(f"[spaces] Failed to download QR asset for {product_id}: {exc}")
        stored_png = None

    if stored_png is not None:
        return _encode_png_bytes(stored_png)

    if cached_b64:
        _persist_qr_png(product_id, base64.b64decode(cached_b64))
        return cached_b64

    return ""


def _resolve_product_id(raw_value: str) -> str:
    if not raw_value.startswith("printpuf://"):
        return raw_value

    parsed = urlparse(raw_value)
    if parsed.scheme != "printpuf":
        raise HTTPException(status_code=400, detail="Unsupported QR payload format.")

    encoded_payload = parse_qs(parsed.query).get("data", [None])[0]
    if not encoded_payload:
        raise HTTPException(
            status_code=400, detail="QR payload is missing its signed data block."
        )

    payload = cbor2.loads(base64.urlsafe_b64decode(encoded_payload.encode("ascii")))
    product_id = payload.get("pid")
    if not isinstance(product_id, str) or not product_id:
        raise HTTPException(
            status_code=400, detail="QR payload does not contain a valid product id."
        )
    return product_id


def _normalize_enrolment_error(detail: str) -> str:
    if "does not match" in detail and "product_id" in detail:
        return (
            "The uploaded scans belong to a different tag. "
            f"{detail}. Use the current QR shown on this tag page when printing and enrolling."
        )
    if "must contain a decodable QR payload" in detail:
        return (
            "One or more uploaded scans do not contain a readable PrintPUF QR payload. "
            "Retake the photos with the full tag visible and the QR region in focus."
        )
    return detail


async def _require_vendor_id(
    session: AsyncSession, vendor_id: str | None
) -> str | None:
    normalized_vendor_id = vendor_id.strip() if isinstance(vendor_id, str) else None
    if not normalized_vendor_id:
        return None

    vendor_statement = select(User.id).where(User.vendor_id == normalized_vendor_id)
    vendor_result = await session.exec(vendor_statement)
    vendor = vendor_result.first()
    if not vendor:
        print(f"[tags] Rejected unknown vendor_id={normalized_vendor_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vendor '{normalized_vendor_id}' not found.",
        )

    return normalized_vendor_id


@router.post("/payment/initiate", response_model=TagPaymentInitiateResponse)
async def initiate_tag_payment(
    payload: TagPaymentInitiateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if current_user.role != UserRole.BRAND:
        raise HTTPException(
            status_code=403, detail="Only Brands can create tag payments."
        )

    vendor_id = await _require_vendor_id(session, payload.vendor_id)
    print(
        "[tags] Initiating tag payment "
        f"brand_id={current_user.id} product_type={payload.product_type!r} vendor_id={vendor_id!r}"
    )

    result = await initiate_squad_transaction(
        email=current_user.email,
        amount=COST_PER_TAG_KOBO,
        customer_name=current_user.full_name or current_user.email,
        metadata={
            "purpose": "tag_generation",
            "brand_id": current_user.id,
            "product_type": payload.product_type,
            "vendor_id": vendor_id,
        },
    )
    return TagPaymentInitiateResponse(
        **result, email=current_user.email, currency="NGN"
    )


@router.post("/generate", response_model=TagGenerateResponse)
async def generate_tag(
    product_type: str = Form(...),
    transaction_ref: str | None = Form(default=None),
    vendor_id: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if current_user.role != UserRole.BRAND:
        raise HTTPException(status_code=403, detail="Only Brands can generate tags.")

    if not transaction_ref:
        if settings.SKIP_PAYMENT_VERIFICATION:
            transaction_ref = f"BYPASS_{uuid.uuid4().hex[:12]}"
            print(f"Bypassing payment for tag generation: {transaction_ref}")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="transaction_ref is required when payment verification is enabled.",
            )

    existing_tag_statement = select(Product).where(
        Product.transaction_ref == transaction_ref
    )
    existing_tag = (await session.exec(existing_tag_statement)).first()
    if existing_tag:
        raise HTTPException(
            status_code=409,
            detail="This transaction reference has already been used to generate a tag.",
        )

    await verify_squad_transaction(transaction_ref, COST_PER_TAG_KOBO)
    normalized_vendor_id = await _require_vendor_id(session, vendor_id)
    print(
        "[tags] Generating tag "
        f"brand_id={current_user.id} transaction_ref={transaction_ref} vendor_id={normalized_vendor_id!r}"
    )

    product_id = uuid.uuid4().hex
    generated_tag = await engine.generate_tag(
        product_id=product_id, vendor_id=normalized_vendor_id
    )
    _persist_qr_png(product_id, generated_tag.qr_png_bytes)

    product = Product(
        id=product_id,
        brand_id=current_user.id,
        vendor_id=normalized_vendor_id,
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
        qr_png_b64=_resolve_qr_png_b64(product.id, product.qr_png_b64),
        status=product.status,
        created_at=product.created_at,
    )


@router.post("/enrol", response_model=TagEnrolResponse)
async def enrol_tag(
    product_id: str = Form(...),
    images: list[UploadFile] = File(
        ..., description="Exactly three enrolment scans of the same tag"
    ),
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

    print(
        "[tags] Starting tag enrolment "
        f"brand_id={current_user.id} product_id={product.id} vendor_id={product.vendor_id!r} "
        f"scan_count={len(images)}"
    )

    image_bytes = [await image.read() for image in images]
    try:
        enrolment_result = await engine.enrol_tag(
            image_source=image_bytes,
            product_id=product.id,
            vendor_id=product.vendor_id,
            required_scan_count=REQUIRED_ENROLMENT_SCANS,
        )
    except ValueError as exc:
        detail = _normalize_enrolment_error(str(exc))
        print(
            "[tags] Rejected tag enrolment "
            f"brand_id={current_user.id} product_id={product.id} reason={detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc

    product.enrolment_bundle = serialize_enrolment_bundle(
        enrolment_result, vendor_id=product.vendor_id
    )
    _persist_qr_png(product.id, enrolment_result.updated_qr_png_bytes)
    product.qr_png_b64 = _encode_png_bytes(enrolment_result.updated_qr_png_bytes)
    product.enrolment_scan_count = enrolment_result.scan_count
    product.status = "enrolled"
    product.enrolled_at = datetime.utcnow()
    product.updated_at = datetime.utcnow()
    session.add(product)
    await session.commit()
    await session.refresh(product)
    print(
        "[tags] Completed tag enrolment "
        f"brand_id={current_user.id} product_id={product.id} vendor_id={product.vendor_id!r} "
        f"scan_count={product.enrolment_scan_count}"
    )

    return TagEnrolResponse(
        product_id=product.id,
        brand_id=product.brand_id,
        vendor_id=product.vendor_id,
        product_type=product.product_type,
        status=product.status,
        enrolment_scan_count=product.enrolment_scan_count,
        qr_png_b64=_resolve_qr_png_b64(product.id, product.qr_png_b64),
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

    statement = (
        select(Product)
        .where(Product.brand_id == current_user.id)
        .order_by(Product.created_at.desc())
    )
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
                qr_png_b64=_resolve_qr_png_b64(product.id, product.qr_png_b64),
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
    device_hash: str | None = Form(
        default=None, description="Browser fingerprint for anonymous tracking"
    ),
    session: AsyncSession = Depends(get_db_session),
):
    image_bytes = await image.read()
    resolved_product_id = _resolve_product_id(product_id)
    product_record = await session.get(Product, resolved_product_id)

    if product_record and product_record.enrolment_bundle is not None:
        result = await engine.verify_tag(
            image_bytes=image_bytes,
            product_id=resolved_product_id,
            enrolment_bundle=product_record.enrolment_bundle,
        )
    else:
        result = await engine.verify_tag(
            image_bytes=image_bytes,
            product_id=resolved_product_id,
            enrolment_bundle=None,
        )

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
            f"(ID%3A%20{resolved_product_id}).%20Report%20to%20NAFDAC."
        )

    scan_event = ScanEvent(
        product_id=resolved_product_id,
        vendor_id=vendor_id,
        verdict=result.verdict,
        score=result.score,
        device_hash=device_hash,
    )
    session.add(scan_event)
    await session.commit()

    return ScanResultResponse(
        product_id=resolved_product_id,
        verdict=result.verdict,
        score=result.score,
        product=product_details,
        vendor=vendor_trust,
        report_url=report_url,
    )
