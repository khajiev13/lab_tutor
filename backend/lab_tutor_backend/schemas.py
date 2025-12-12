from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import UserRole


class UserBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role: UserRole


class UserRead(UserBase):
    id: int
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: EmailStr | None = None


class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class CourseRead(BaseModel):
    id: int
    title: str
    description: str | None
    teacher_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnrollmentRead(BaseModel):
    id: int
    course_id: int
    student_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

