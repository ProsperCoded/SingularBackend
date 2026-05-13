from schemas.webhook import WebhookResponse
from models.user import User
from models.user import UserRole
from core.config import settings
from fastapi import Depends, HTTPException, Request, APIRouter
from sqlmodel.ext.asyncio.session import AsyncSession
from core.database import get_db_session
from svix.webhooks import Webhook, WebhookVerificationError

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/clerk", response_model=WebhookResponse)
async def webhook(request: Request, session: AsyncSession = Depends(get_db_session)):
    """
    Handle webhook events from Clerk (User creation and deletion).
    """
    payload = await request.json()
    headers = request.headers

    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=400, detail="Missing Svix headers")

    svix_headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }

    wh = Webhook(settings.CLERK_WEBHOOK_SECRET)

    try:
        event = wh.verify(payload, svix_headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type")
    data = event.get("data", {})

    # Handle the different webhook events
    if event_type == "user.created":
        user_id = data.get("id")
        emails = data.get("email_addresses", [])
        primary_email = emails[0].get("email_address") if emails else ""

        # Extract the user's role from Clerk's metadata
        metadata = data.get("public_metadata", {})
        if not metadata:
            metadata = data.get("unsafe_metadata", {})
        raw_role = metadata.get("role", "brand").lower()

        try:
            assigned_role = UserRole(raw_role)
        except ValueError:
            assigned_role = UserRole.BRAND

        new_user = User(id=user_id, email=primary_email, role=assigned_role)
        session.add(new_user)
        await session.commit()
        print(f"Successfully synced new user: {primary_email} as {assigned_role.value}")

    elif event_type == "user.deleted":
        user_id = data.get("id")
        user = await session.get(User, user_id)
        if user:
            await session.delete(user)
            await session.commit()
            print("User deleted")

    return {"success": True}
