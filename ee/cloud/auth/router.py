"""Auth domain — FastAPI router."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ee.cloud.auth.core import (
    UserCreate,
    UserRead,
    bearer_backend,
    cookie_backend,
    current_active_user,
    fastapi_users,
)
from ee.cloud.auth.schemas import ProfileUpdateRequest, SetWorkspaceRequest
from ee.cloud.auth.service import AuthService
from ee.cloud.models.user import User

router = APIRouter(tags=["Auth"])

# Avatar storage — local filesystem for now (could swap for S3/R2 later)
_AVATAR_DIR = Path.home() / ".pocketpaw" / "avatars"
_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
_ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# fastapi-users auth routes (login/logout)
# ---------------------------------------------------------------------------

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


@router.get("/auth/me")
async def get_me(user: User = Depends(current_active_user)):
    return await AuthService.get_profile(user)


@router.patch("/auth/me")
async def update_me(
    body: ProfileUpdateRequest,
    user: User = Depends(current_active_user),
):
    return await AuthService.update_profile(user, body)


@router.post("/auth/set-active-workspace")
async def set_active_workspace(
    body: SetWorkspaceRequest,
    user: User = Depends(current_active_user),
):
    await AuthService.set_active_workspace(user, body.workspace_id)
    return {"ok": True, "activeWorkspace": body.workspace_id}


@router.post("/auth/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
):
    """Upload a profile picture. Returns the updated profile with the avatar URL."""
    if file.content_type not in _ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_AVATAR_TYPES)}",
        )

    content = await file.read()
    if len(content) > _MAX_AVATAR_SIZE:
        raise HTTPException(status_code=413, detail="Avatar must be under 5MB")

    # Determine extension from content-type
    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    ext = ext_map.get(file.content_type or "", ".png")
    filename = f"{user.id}{ext}"
    dest = _AVATAR_DIR / filename

    # Remove any old avatar with a different extension
    for old in _AVATAR_DIR.glob(f"{user.id}.*"):
        if old.name != filename:
            try:
                old.unlink()
            except OSError:
                pass

    dest.write_bytes(content)

    # Update user record — store a relative API path
    avatar_path = f"/api/v1/auth/avatar/{filename}"
    user.avatar = avatar_path
    await user.save()

    return await AuthService.get_profile(user)


@router.get("/auth/avatar/{filename}")
async def get_avatar(filename: str):
    """Serve a user's avatar file."""
    from fastapi.responses import FileResponse

    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = _AVATAR_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found")

    return FileResponse(path)
