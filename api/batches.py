from services.dummy_engine import engine
from core.storage import upload_multiple_batch_files
import uuid
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from core.auth import get_current_user
from core.database import get_db_session
from core.payment import verify_squad_transaction

from models.user import User, UserRole
from models.batch import Batch
from schemas.batch import (
    BatchGenerateRequest,
    BatchResponse,
    BatchItemResponse,
    BrandBatchesResponse,
)

router = APIRouter(prefix="/batch", tags=["Batches"])

COST_PER_TAG_KOBO = 150  # 1.5 Naira
BATCH_EXPIRY_DAYS = 30


@router.post("/generate", response_model=BatchResponse)
async def generate_batch(
    request: BatchGenerateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Generate a new batch of PUF tags.
    Verifies the Squad payment transaction before triggering the Core Engine
    to generate the printable PDF assets.
    """
    if current_user.role != UserRole.BRAND:
        raise HTTPException(status_code=403, detail="Only Brands can generate tags.")

    existing_batch_statement = select(Batch).where(
        Batch.transaction_ref == request.transaction_ref
    )
    existing_batch = (await session.exec(existing_batch_statement)).first()

    if existing_batch:
        raise HTTPException(
            status_code=409,
            detail="This transaction reference has already been used to generate a batch.",
        )

    expected_cost = request.quantity * COST_PER_TAG_KOBO
    await verify_squad_transaction(request.transaction_ref, expected_cost)

    # Generate the PDF via the engine
    generated_pages = await engine.generate_batch(
        quantity=request.quantity,
        product_type=request.product_type,
        vendor_id=request.vendor_id,
    )

    if not generated_pages:
        raise HTTPException(
            status_code=500,
            detail="The PUF Core Engine failed to generate the assets.",
        )

    batch_uuid = uuid.uuid4().hex
    download_urls = await upload_multiple_batch_files(generated_pages, batch_uuid)

    if len(download_urls) != len(generated_pages):
        raise HTTPException(
            status_code=500,
            detail="Cloud storage failed. Some pages were dropped during upload.",
        )

    new_batch = Batch(
        brand_id=current_user.id,
        vendor_id=request.vendor_id,
        product_type=request.product_type,
        quantity=request.quantity,
        transaction_ref=request.transaction_ref,
        download_urls=download_urls,
    )

    session.add(new_batch)
    await session.commit()
    await session.refresh(new_batch)

    return new_batch


@router.get("/list", response_model=BrandBatchesResponse)
async def list_batches(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    List all batches for the authenticated brand.
    Each batch includes a 30-day expiry window and active status.
    """

    if current_user.role != UserRole.BRAND:
        raise HTTPException(status_code=403, detail="Only Brands can view batches.")

    statement = (
        select(Batch)
        .where(Batch.brand_id == current_user.id)
        .order_by(Batch.created_at.desc())
    )
    results = await session.exec(statement)
    batches = results.all()

    now = datetime.utcnow()
    items = []

    for batch in batches:
        expires_at = batch.created_at + timedelta(days=BATCH_EXPIRY_DAYS)
        is_active = now < expires_at

        # Use the first download URL as the primary link
        download_url = batch.download_urls[0] if batch.download_urls else ""

        items.append(
            BatchItemResponse(
                batch_id=batch.id,
                date_generated=batch.created_at,
                quantity=batch.quantity,
                product_type=batch.product_type,
                vendor_id=batch.vendor_id,
                download_url=download_url,
                expires_at=expires_at,
                is_active=is_active,
            )
        )

    return BrandBatchesResponse(batches=items)
