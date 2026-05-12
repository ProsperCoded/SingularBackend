import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from wonderwords import RandomWord
from core.database import get_session
from core.auth import get_current_user
from models.user import User, UserRole

router = APIRouter(prefix="/vendors", tags=["Vendors"])
LOCATIONS = ["lagos", "abuja", "kano", "phc", "ibadan", "enugu"]
word_generator = RandomWord()


@router.get("/generate-id")
async def generate_vendor_id(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
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
