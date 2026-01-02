from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from .dependencies import (
    auth_backend,
    create_refresh_token,
    fastapi_users,
    get_user_db,
    get_user_manager,
    verify_refresh_token,
)
from .schemas import Token, UserCreate, UserRead, UserUpdate
from fastapi_users.db import SQLAlchemyUserDatabase
from app.modules.auth.models import User

router = APIRouter()

# Custom login endpoint that includes refresh token
@router.post("/auth/jwt/login", response_model=Token, tags=["auth"])
async def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager=Depends(get_user_manager),
):
    """Login endpoint that returns both access and refresh tokens."""
    user = await user_manager.authenticate(credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="LOGIN_BAD_CREDENTIALS",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="LOGIN_USER_NOT_ACTIVE",
        )
    
    # Generate access token using the strategy
    strategy = auth_backend.get_strategy()
    access_token = await strategy.write_token(user)
    refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/auth/jwt/refresh", response_model=Token, tags=["auth"])
async def refresh_token_endpoint(
    refresh_token: str = Body(..., embed=True),
    user_db: SQLAlchemyUserDatabase[User, int] = Depends(get_user_db),
):
    """Refresh access token using refresh token."""
    user_id = verify_refresh_token(refresh_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    user = await user_db.get(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    # Generate new access token
    strategy = auth_backend.get_strategy()
    access_token = await strategy.write_token(user)
    # Optionally rotate refresh token (for security)
    new_refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
