"""Hardware telemetry router (/system/telemetry)."""
from __future__ import annotations

from fastapi import APIRouter

from .deps import AppContext


def create_telemetry_router(_ctx: AppContext) -> APIRouter:
    router = APIRouter()

    @router.get("/system/telemetry")
    async def system_telemetry():
        from ..tools.system_telemetry import get_system_status
        return {"ok": True, "telemetry": get_system_status()}

    return router
