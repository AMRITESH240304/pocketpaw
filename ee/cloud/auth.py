"""Enterprise auth — fastapi-users with JWT cookie + bearer transport.

Provides:
- POST /auth/register — sign up with email + password
- POST /auth/login — sign in, returns JWT cookie + token
- POST /auth/logout — clear cookie
- GET  /auth/me — current user
- PATCH /auth/me — update profile

Admin seeding: call seed_admin() on startup to ensure a default admin exists.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users_db_beanie import BeanieUserDatabase, ObjectIDIDMixin
from fastapi_users import schemas as fastapi_users_schemas
from pydantic import BaseModel

from ee.cloud.models.user import OAuthAccount, User, WorkspaceMembership

logger = logging.getLogger(__name__)

SECRET = os.environ.get("AUTH_SECRET", "change-me-in-production-please")
TOKEN_LIFETIME = 60 * 60 * 24 * 7  # 7 days


# ---------------------------------------------------------------------------
# User database adapter
# ---------------------------------------------------------------------------

async def get_user_db():
    yield BeanieUserDatabase(User, OAuthAccount)


# ---------------------------------------------------------------------------
# User manager (handles registration, password hashing, etc.)
# ---------------------------------------------------------------------------

class UserManager(ObjectIDIDMixin, BaseUserManager[User, PydanticObjectId]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Request | None = None):
        logger.info("User registered: %s (%s)", user.email, user.id)

    async def on_after_login(self, user: User, request: Request | None = None, response=None):
        logger.debug("User logged in: %s", user.email)


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


# ---------------------------------------------------------------------------
# Auth backends — cookie (browser) + bearer (API/Tauri)
# ---------------------------------------------------------------------------

cookie_transport = CookieTransport(
    cookie_name="paw_auth",
    cookie_max_age=TOKEN_LIFETIME,
    cookie_secure=False,  # Set True in production with HTTPS
    cookie_samesite="lax",
)

bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=TOKEN_LIFETIME)


cookie_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

bearer_backend = AuthenticationBackend(
    name="bearer",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# ---------------------------------------------------------------------------
# FastAPIUsers instance
# ---------------------------------------------------------------------------

fastapi_users = FastAPIUsers[User, PydanticObjectId](
    get_user_manager,
    [cookie_backend, bearer_backend],
)

# Current user dependencies
current_active_user = fastapi_users.current_user(active=True)
current_optional_user = fastapi_users.current_user(active=True, optional=True)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Schemas for register/read
# ---------------------------------------------------------------------------

class UserRead(fastapi_users_schemas.BaseUser[PydanticObjectId]):
    full_name: str = ""
    avatar: str = ""


class UserCreate(fastapi_users_schemas.BaseUserCreate):
    full_name: str = ""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(tags=["Auth"])

# Auth routes (login/logout)
router.include_router(
    fastapi_users.get_auth_router(cookie_backend),
    prefix="/auth",
)
router.include_router(
    fastapi_users.get_auth_router(bearer_backend),
    prefix="/auth/bearer",
)

# Register route
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
)


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    full_name: str | None = None
    avatar: str | None = None


@router.get("/auth/me")
async def get_me(user: User = Depends(current_active_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.full_name,
        "image": user.avatar,
        "emailVerified": user.is_verified,
        "activeWorkspace": user.active_workspace,
        "workspaces": [
            {"workspace": w.workspace, "role": w.role}
            for w in user.workspaces
        ],
    }


@router.patch("/auth/me")
async def update_me(
    body: ProfileUpdate,
    user: User = Depends(current_active_user),
):
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.avatar is not None:
        user.avatar = body.avatar
    await user.save()
    return await get_me(user)


@router.post("/auth/set-active-workspace")
async def set_active_workspace(
    body: dict,
    user: User = Depends(current_active_user),
):
    ws_id = body.get("workspaceId") or body.get("organizationId")
    if not ws_id:
        from fastapi import HTTPException
        raise HTTPException(400, "workspaceId required")
    user.active_workspace = ws_id
    await user.save()
    return {"ok": True, "activeWorkspace": ws_id}


# ---------------------------------------------------------------------------
# Admin seeding
# ---------------------------------------------------------------------------

async def seed_admin(
    email: str | None = None,
    password: str | None = None,
    full_name: str | None = None,
) -> User | None:
    """Create default admin user if it doesn't exist.

    Reads from env vars if args not provided:
      ADMIN_EMAIL (default: admin@pocketpaw.ai)
      ADMIN_PASSWORD (default: admin123)
      ADMIN_NAME (default: Admin)
    """
    email = email or os.environ.get("ADMIN_EMAIL", "admin@pocketpaw.ai")
    password = password or os.environ.get("ADMIN_PASSWORD", "admin123")
    full_name = full_name or os.environ.get("ADMIN_NAME", "Admin")

    existing = await User.find_one(User.email == email)
    if existing:
        logger.debug("Admin user already exists: %s", email)
        return existing

    from fastapi_users.exceptions import UserAlreadyExists

    db = BeanieUserDatabase(User, OAuthAccount)
    manager = UserManager(db)
    try:
        user = await manager.create(
            UserCreate(
                email=email,
                password=password,
                full_name=full_name,
                is_superuser=True,
                is_verified=True,
            ),
        )
        user.full_name = full_name
        await user.save()
        logger.info("Admin user created: %s (password: %s)", email, password)
        return user
    except UserAlreadyExists:
        return await User.find_one(User.email == email)
    except Exception as exc:
        logger.error("Failed to seed admin: %s", exc)
        return None
