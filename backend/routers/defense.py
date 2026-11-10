"""Academic Thesis Defense Co-Pilot router (/defense/*)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .deps import AppContext


def create_defense_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    orchestrator = ctx.orchestrator
    audit = ctx.audit

    @router.get("/defense/status")
    async def defense_status():
        return {"ok": True, "pacing": orchestrator.defense_copilot.get_pacing_status()}

    @router.get("/defense/sessions")
    async def defense_sessions(limit: int = 10):
        return {"ok": True, "sessions": audit.list_defense_sessions(limit=limit)}

    @router.get("/defense/qa-bank")
    async def defense_qa_bank(category: str | None = None):
        return {"ok": True, "items": orchestrator.defense_copilot.get_defense_bank(category=category)}

    @router.post("/defense/evaluate")
    async def defense_evaluate(body: dict):
        qa_id = body.get("qa_id", "")
        answer = body.get("answer", "")
        if not qa_id or not answer:
            raise HTTPException(400, "qa_id and answer are required.")
        eval_result = orchestrator.defense_copilot.evaluate_answer(qa_id, answer)
        return {"ok": True, "evaluation": eval_result}

    return router
