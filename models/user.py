from datetime import datetime
from enum import Enum
from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    BRAND = "brand"
    VENDOR = "vendor"


class User(SQLModel, table=True):
    id: str = Field(primary_key=True, description="Clerk's unique user ID")
    email: str = Field(unique=True, index=True)
    role: UserRole = Field(default=UserRole.BRAND)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    vendor_id: str | None = Field(default=None, unique=True)
    
