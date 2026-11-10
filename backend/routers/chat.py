"""Chat, confirmation, SSE event streaming, priority emails, calendar, and measurable tasks router."""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..tools.email_listener import email_event_dispatcher
from .deps import HELPER_FILE, AppContext, ChatIn, ConfirmIn
from ..core.llm import LLMError
from ..tools.meeting import translation_prompt
from .deps import require_full


class MeetingTranslationIn(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


def create_chat_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    orchestrator = ctx.orchestrator
    audit = ctx.audit
    translation_lock = asyncio.Lock()

    @router.post("/meeting/translate")
    async def translate_meeting(body: MeetingTranslationIn, request: Request):
        require_full(request)
        if not body.text.strip():
            raise HTTPException(422, "Transcript is empty")
        if not ctx.settings.llm_enabled:
            raise HTTPException(503, "Enable Nightmare's agy provider to translate meeting captions")
        if translation_lock.locked():
            raise HTTPException(429, "A meeting translation is already running; try again shortly")
        async with translation_lock:
            try:
                # Use the shared model lock; no routing, actions, or conversation memory.
                result = await orchestrator._ask(translation_prompt(body.text), smart=True)
            except LLMError:
                raise HTTPException(503, "Meeting translation unavailable. Check agy sign-in and try again.")
        return {"translation": result}

    @router.post("/chat")
    async def chat(body: ChatIn, request: Request):
        readonly = getattr(request.state, "role", "full") == "readonly"
        session = getattr(request.state, "memory_key", "default")
        return (await orchestrator.handle(body.text, readonly=readonly, session=session)).to_dict()

    @router.post("/session/reset")
    async def session_reset(request: Request):
        """/clear and /new: forget this login's conversation so the next message starts fresh."""
        orchestrator.reset_session(getattr(request.state, "memory_key", "default"))
        return {"ok": True}

    @router.get("/help")
    async def help_text():
        """The command list shown by /help, read straight from nightmare_helper.txt."""
        try:
            return {"text": HELPER_FILE.read_text(encoding="utf-8")}
        except OSError:
            raise HTTPException(404, "nightmare_helper.txt is missing from the project folder.")

    @router.post("/confirm")
    async def confirm(body: ConfirmIn, request: Request):
        if getattr(request.state, "role", "full") == "readonly":
            audit.log_action("confirm", body.id, "blocked_readonly")
            raise HTTPException(403, "Read-only session cannot approve actions")
        session_key = getattr(request.state, "memory_key", "default")
        return (await orchestrator.confirm(body.id, body.approve, session=session_key)).to_dict()

    @router.get("/audit")
    async def recent():
        return {"actions": audit.recent_actions()}

    # ---- Real-Time Server-Sent Events (SSE) Stream ----

    @router.get("/events")
    async def events_stream(request: Request):
        """Server-Sent Events endpoint pushing real-time notifications to frontend clients."""
        email_event_dispatcher.set_loop(asyncio.get_running_loop())
        queue = email_event_dispatcher.subscribe()

        async def event_generator():
            try:
                yield {
                    "event": "connected",
                    "data": json.dumps({"status": "connected", "time": time.time()}),
                }
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                        event_type = payload.get("type", "message")
                        yield {
                            "event": event_type,
                            "data": json.dumps(payload),
                        }
                    except asyncio.TimeoutError:
                        continue
            except (asyncio.CancelledError, GeneratorExit):
                pass
            finally:
                email_event_dispatcher.unsubscribe(queue)

        return EventSourceResponse(
            event_generator(),
            ping=15,
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- Real-Time Pub/Sub Priority Emails ----

    @router.get("/emails/priority")
    async def emails_priority(limit: int = 50, status: str | None = None, category: str | None = None):
        """Returns recent emails categorized as Priority (or matching category) by the background listener."""
        return await asyncio.to_thread(audit.get_priority_emails, limit=limit, status=status, category=category)

    @router.post("/emails/{email_id}/status")
    async def update_email_status(email_id: str, body: dict):
        """Update email status (e.g. 'Read', 'Pending', 'Acknowledged')."""
        status = body.get("status", "Read")
        ok = await asyncio.to_thread(audit.update_email_status, email_id, status)
        return {"ok": ok, "id": email_id, "status": status}

    # ---- Calendar & Measurable Tasks APIs ----

    @router.get("/calendar/events")
    async def get_calendar_events(start: str | None = None, end: str | None = None):
        """Returns calendar events, optionally bounded by start/end ISO dates."""
        if start and end:
            return await asyncio.to_thread(audit.get_calendar_events_in_range, start, end)
        return await asyncio.to_thread(audit.list_calendar_events)

    @router.post("/calendar/events")
    async def create_calendar_event(body: dict):
        title = body.get("title", "").strip()
        if not title:
            raise HTTPException(400, "Title is required")
        ev_type = body.get("event_type", "meeting").strip()
        start_date = body.get("start_date", "").strip()
        end_date = body.get("end_date")
        ev = await asyncio.to_thread(audit.add_calendar_event, title, ev_type, start_date, end_date)
        return {"ok": True, "event": ev}

    @router.get("/tasks/measurable")
    async def get_measurable_tasks():
        """Returns all measurable tasks with current and target progress."""
        return await asyncio.to_thread(audit.list_measurable_tasks)

    @router.post("/tasks/measurable")
    async def create_or_update_measurable_task(body: dict):
        title = body.get("title", "").strip()
        if not title:
            raise HTTPException(400, "Title is required")
        curr = int(body.get("current_progress", 0))
        tgt = int(body.get("target_progress", 0))
        unit = body.get("unit", "").strip()
        task = await asyncio.to_thread(
            audit.update_measurable_task_progress, title, current_progress=curr, target_progress=tgt, unit=unit
        )
        return {"ok": True, "task": task}

    return router
