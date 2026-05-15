from schemas.vendor import (
    GenerateVendorIdResponse,
    CheckVendorIdResponse,
    ConfirmVendorIdResponse,
    ConfirmVendorId,
    VendorDashboardResponse,
    ScanStats,
    VendorDirectoryResponse,
    VendorDirectoryItem,
)
from services.trust import compute_trust_score, compute_score_trend
from core.database import get_db_session
from fastapi import Query
import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from wonderwords import RandomWord
from core.auth import get_current_user
from models.user import User, UserRole

router = APIRouter(prefix="/vendors", tags=["Vendors"])
LOCATIONS = ["lagos", "abuja", "kano", "phc", "ibadan", "enugu"]
word_generator = RandomWord()


@router.get("/generate-id", response_model=GenerateVendorIdResponse)
async def generate_vendor_id(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Generate a unique Vendor ID for a new vendor account.
    Returns a candidate ID (e.g., 'swift-mango-lagos') that the vendor can review before confirming.
    """
    # Enforce role-based access
    if current_user.role != UserRole.VENDOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Vendor accounts can generate Vendor IDs.",
        )

    # Prevent overwriting an existing ID
    if getattr(current_user, "vendor_id", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already confirmed a Vendor ID.",
        )

    max_attempts = 10
    attempts = 0
    generated_id = ""
    is_unique = False

    while attempts < max_attempts and not is_unique:
        attempts += 1

        adj = word_generator.word(include_parts_of_speech=["adjectives"])
        noun = word_generator.word(include_parts_of_speech=["nouns"])
        loc = random.choice(LOCATIONS)

        candidate_id = f"{adj}-{noun}-{loc}".lower()
        statement = select(User).where(User.vendor_id == candidate_id)
        result = await session.exec(statement)
        existing_user = result.first()

        if not existing_user:
            generated_id = candidate_id
            is_unique = True

    if not is_unique:
        random_suffix = random.randint(1000, 9999)
        adj = word_generator.word(include_parts_of_speech=["adjectives"])
        noun = word_generator.word(include_parts_of_speech=["nouns"])
        generated_id = f"{adj}-{noun}-{random_suffix}".lower()

    return {"generated_id": generated_id}


@router.get("/check-id", response_model=CheckVendorIdResponse)
async def check_vendor_id(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    id: str = Query(..., description="The Vendor ID to check"),
):
    """
    Check if a specific Vendor ID is available.
    Returns `available: True` if no other vendor has claimed it.
    """

    if current_user.role != UserRole.VENDOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Vendor accounts can check Vendor IDs.",
        )

    get_user_with_id_statement = select(User.id).where(User.vendor_id == id)
    result = await session.exec(get_user_with_id_statement)
    existing_user = result.first()

    if existing_user:
        return {"available": False}

    return {"available": True}


@router.post("/confirm-id", response_model=ConfirmVendorIdResponse)
async def confirm_vendor_id(
    payload: ConfirmVendorId,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Confirm and claim a Vendor ID.
    Once claimed, this ID becomes the vendor's permanent identifier.
    """

    if current_user.role != UserRole.VENDOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Vendor accounts can confirm Vendor IDs.",
        )

    # Prevent overwriting an existing ID
    if getattr(current_user, "vendor_id", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already confirmed a Vendor ID.",
        )

    get_vendor_with_id_statement = select(User.id).where(User.vendor_id == payload.vendor_id)
    result = await session.exec(get_vendor_with_id_statement)
    existing_vendor = result.first()

    if existing_vendor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor ID already taken.",
        )

    current_user.vendor_id = payload.vendor_id
    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)

    return {
        "message": "Vendor ID confirmed successfully",
        "vendor_id": current_user.vendor_id,
    }


@router.get("/dashboard", response_model=VendorDashboardResponse)
async def get_vendor_dashboard(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Trust score dashboard for the authenticated vendor.
    Returns their score, badge tier, trend, and scan stats.
    """

    if current_user.role != UserRole.VENDOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Vendor accounts can view the vendor dashboard.",
        )

    if not current_user.vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You have not confirmed a Vendor ID yet.",
        )

    vendor_id = current_user.vendor_id

    trust_score, badge_tier, stats = await compute_trust_score(session, vendor_id)
    score_trend = await compute_score_trend(session, vendor_id)

    return VendorDashboardResponse(
        vendor_id=vendor_id,
        trust_score=trust_score,
        badge_tier=badge_tier,
        score_trend=score_trend,
        stats=ScanStats(**stats),
    )


@router.get("/directory", response_model=VendorDirectoryResponse)
async def get_vendor_directory(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Public directory of all registered vendors.
    Available to Brands to browse potential distribution partners.
    """
    if current_user.role != UserRole.BRAND:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Brands can view the vendor directory.",
        )

    # Get all users who have confirmed a vendor_id
    statement = select(User).where(User.vendor_id.isnot(None))
    result = await session.exec(statement)
    vendor_users = result.all()

    directory_items = []
    for vendor_user in vendor_users:
        vendor_id = vendor_user.vendor_id
        # We know vendor_id exists here because of the query filter
        trust_score, badge_tier, stats = await compute_trust_score(session, vendor_id)
        directory_items.append(
            VendorDirectoryItem(
                vendor_id=vendor_id,
                full_name=vendor_user.full_name,
                trust_score=trust_score,
                badge_tier=badge_tier,
                total_scans=stats["total_scans"],
            )
        )

    return VendorDirectoryResponse(vendors=directory_items)
