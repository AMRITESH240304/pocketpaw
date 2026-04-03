"""License status endpoint — no license required to check status."""

from __future__ import annotations

from fastapi import APIRouter

from ee.cloud.license import LicenseInfo, get_license_info

router = APIRouter(tags=["License"])


@router.get("/license")
async def license_status() -> LicenseInfo:
    """Check enterprise license status. No auth required."""
    return get_license_info()
