"""Shared FastAPI dependencies for cloud routers."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from ee.cloud.auth import current_active_user
from ee.cloud.models.user import User


async def get_current_user(user: User = Depends(current_active_user)) -> User:
    """Get the authenticated user from JWT token."""
    return user


async def get_user_id(user: User = Depends(current_active_user)) -> str:
    """Extract user ID from JWT token."""
    return str(user.id)


async def get_workspace_id(user: User = Depends(current_active_user)) -> str:
    """Extract active workspace ID from the authenticated user."""
    if not user.active_workspace:
        raise HTTPException(400, "No active workspace. Create or join a workspace first.")
    return user.active_workspace


async def get_optional_workspace_id(user: User = Depends(current_active_user)) -> str | None:
    """Extract workspace ID if set, or None."""
    return user.active_workspace
