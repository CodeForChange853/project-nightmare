"""Router miss review queue and exemplar approval router (/router/*)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .deps import AppContext, is_remote


def create_router_review_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    audit = ctx.audit
    settings = ctx.settings

    @router.get("/router/review")
    async def get_router_miss_queue():
        misses = audit.get_router_misses(unreviewed_only=True)
        return {"ok": True, "misses": misses}

    @router.post("/router/approve")
    async def approve_router_miss(body: dict, request: Request):
        if is_remote(request, settings):
            raise HTTPException(status_code=403, detail="Remote sessions are read-only")
        miss_id = body.get("miss_id")
        approved_intent = body.get("approved_intent")
        if not miss_id or not approved_intent:
            raise HTTPException(status_code=400, detail="miss_id and approved_intent required")
        success = audit.approve_router_miss(int(miss_id), approved_intent)
        return {
            "ok": success,
            "message": f"Approved miss #{miss_id} as '{approved_intent}'" if success else "Failed to approve miss",
        }

    return router
