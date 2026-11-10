"""Database viewer router (/db/*)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .deps import (
    DB_TOKEN_HEADER,
    AppContext,
    LoginIn,
    open_with_pin,
    require_full,
)


def create_database_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    audit = ctx.audit
    db_access = ctx.db_access

    def require_db(request: Request) -> None:
        require_full(request)
        if not db_access.valid(request.headers.get(DB_TOKEN_HEADER, "")):
            raise HTTPException(403, "The database is closed. Say “database access open” to open it again.")

    @router.post("/db/open")
    async def db_open(body: LoginIn, request: Request):
        return open_with_pin(body, request, "db", db_access, ctx)

    @router.post("/db/close")
    async def db_close(request: Request):
        db_access.close(request.headers.get(DB_TOKEN_HEADER, ""))
        audit.log_action("db_close", "viewer", "ok")
        return {"ok": True}

    @router.get("/db/records")
    async def db_records(request: Request):
        require_db(request)
        return {
            "counts": audit.table_counts(),
            "notes": audit.list_notes(include_done=True),
            "facts": audit.list_facts(),
            "day_summaries": audit.list_day_summaries(30),
            "actions": audit.recent_actions(limit=200),
            "llm_calls": audit.recent_llm_calls(limit=200),
            "calendar_events": audit.list_calendar_events(),
            "measurable_tasks": audit.list_measurable_tasks(),
        }

    @router.post("/db/calendar/{event_id}/delete")
    async def db_delete_calendar_event(event_id: int, request: Request):
        require_db(request)
        ok = audit.delete_calendar_event(event_id)
        if not ok:
            raise HTTPException(404, "Event not found")
        audit.log_action("delete_calendar_event", f"#{event_id} (database viewer)", "ok")
        return {"ok": True}

    @router.post("/db/tasks/{task_id}/delete")
    async def db_delete_measurable_task(task_id: int, request: Request):
        require_db(request)
        ok = audit.delete_measurable_task(task_id)
        if not ok:
            raise HTTPException(404, "Task not found")
        audit.log_action("delete_measurable_task", f"#{task_id} (database viewer)", "ok")
        return {"ok": True}

    @router.get("/db/actions")
    async def db_actions(
        request: Request,
        group: str = "",
        outcome: str = "",
        q: str = "",
        before: int | None = None,
    ):
        require_db(request)
        return audit.search_actions(group=group, outcome=outcome, query=q, before=before)

    @router.post("/db/notes/{note_id}/delete")
    async def db_delete_note(note_id: int, request: Request):
        require_db(request)
        deleted = audit.delete_note(note_id)
        if deleted is None:
            raise HTTPException(404, "That reminder no longer exists.")
        audit.log_action("delete_note", f"#{note_id} (database viewer)", "ok")
        return {"ok": True, "deleted": deleted}

    @router.post("/db/facts/{fact_id}/delete")
    async def db_delete_fact(fact_id: int, request: Request):
        require_db(request)
        deleted = audit.delete_fact(fact_id)
        if deleted is None:
            raise HTTPException(404, "That memory no longer exists.")
        audit.log_action("forget_fact", f"#{fact_id} (database viewer)", "ok")
        return {"ok": True, "deleted": deleted}

    return router
