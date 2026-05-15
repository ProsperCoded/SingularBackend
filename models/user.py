from datetime import datetime
from enum import Enum
from sqlmodel import Field, SQLModel
import uuid


class UserRole(str, Enum):
    BRAND = "brand"
    VENDOR = "vendor"


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    full_name: str = Field(default="", index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str = Field(default="", repr=False)
    role: UserRole = Field(default=UserRole.BRAND)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    vendor_id: str | None = Field(default=None, unique=True)
    
