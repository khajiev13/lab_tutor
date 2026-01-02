import logging
from collections.abc import AsyncIterator, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
import jwt
from datetime import datetime, timedelta, timezone
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.settings import settings

from .models import User, UserRole
from .neo4j_repository import UserGraphRepository

SECRET = settings.secret_key
logger = logging.getLogger(__name__)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        if request is None:
            return

        driver = getattr(request.app.state, "neo4j_driver", None)
        if driver is None:
            return

        try:
            with driver.session(database=settings.neo4j_database) as session:
                repo = UserGraphRepository(session)
                repo.upsert_user(
                    user_id=user.id,
                    role=user.role.value,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    created_at=user.created_at,
                )
        except Exception:
            logger.exception("Neo4j user upsert failed after register")

    async def on_after_update(
        self,
        user: User,
        update_dict: dict[str, object],
        request: Request | None = None,
    ) -> None:
        if request is None:
            return

        driver = getattr(request.app.state, "neo4j_driver", None)
        if driver is None:
            return

        try:
            with driver.session(database=settings.neo4j_database) as session:
                repo = UserGraphRepository(session)
                repo.upsert_user(
                    user_id=user.id,
                    role=user.role.value,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    created_at=user.created_at,
                )
        except Exception:
            logger.exception("Neo4j user upsert failed after update")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        logger.info("User %s requested password reset", user.id)

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        logger.info("Verification requested for user %s", user.id)


async def get_user_db(
    session: AsyncSession = Depends(get_async_db),
) -> AsyncIterator[SQLAlchemyUserDatabase[User, int]]:
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, int] = Depends(get_user_db),
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=SECRET, lifetime_seconds=settings.access_token_expire_minutes * 60
    )


def create_refresh_token(user_id: int) -> str:
    """Create a refresh token for a user."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, SECRET, algorithm=settings.algorithm)


def verify_refresh_token(token: str) -> int | None:
    """Verify and decode a refresh token, returning user_id if valid."""
    try:
        payload = jwt.decode(token, SECRET, algorithms=[settings.algorithm])
        if payload.get("type") != "refresh":
            return None
        return int(payload.get("sub"))
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)


def require_role(required_role: UserRole) -> Callable[[User], User]:
    async def role_dependency(
        user: User = Depends(current_active_user),
    ) -> User:
        if user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{required_role.value.title()} role required",
            )
        return user

    return role_dependency
