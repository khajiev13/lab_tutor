from datetime import datetime

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr, field_validator

from .models import UserRole


class UserRead(schemas.BaseUser[int]):
    first_name: str
    last_name: str
    role: UserRole
    created_at: datetime


class UserCreate(schemas.BaseUserCreate):
    first_name: str
    last_name: str
    role: UserRole


class UserUpdate(schemas.BaseUserUpdate):
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    def email_must_not_be_empty(cls, v: EmailStr) -> EmailStr:
        if not v or v.strip() == "":
            raise ValueError("Email must not be empty")
        if "@" not in v:
            raise ValueError("Invalid email format")
        if "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: EmailStr | None = None
