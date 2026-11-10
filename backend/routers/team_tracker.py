"""CitizenGraph 4-Tab Telemetry, GDrive Diff, and Team Quota Tracker router (/team-tracker/*)."""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Request

from .deps import AppContext, is_remote


def create_team_tracker_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    settings = ctx.settings
    audit = ctx.audit
    orchestrator = ctx.orchestrator

    @router.get("/team-tracker/progress")
    async def team_tracker_progress(team: str | None = None):
        from ..tools.team_tracker import scan_team_progress
        scan = await asyncio.to_thread(
            scan_team_progress,
            settings=settings,
            audit=audit,
            team_filter=team,
        )
        return scan

    @router.post("/team-tracker/nudge")
    async def team_tracker_nudge(body: dict, request: Request):
        if is_remote(request, settings):
            audit.log_action("send_team_nudge", f"nudge {body.get('task_id')}", "blocked_remote")
            raise HTTPException(403, "Generating reminder emails is blocked on remote sessions.")

        task_id = body.get("task_id", "")
        from ..core.actions import plan_send_team_nudge
        from ..tools.email_notifier import create_nudge_email_draft

        state = audit.get_team_task_state(task_id)
        if not state:
            raise HTTPException(404, f"Task {task_id} not found in state store.")

        subj, email_body, _ = create_nudge_email_draft(
            to_email=state["owner_email"],
            assigned_team=state["assigned_team"],
            task_name=state["task_name"],
            current_count=state["current_count"],
            target_count=state["target_count"],
            days_stale=state["days_since_update"],
        )
        plan = plan_send_team_nudge(
            task_id=state["task_id"],
            assigned_team=state["assigned_team"],
            owner_email=state["owner_email"],
            task_name=state["task_name"],
            current_count=state["current_count"],
            target_count=state["target_count"],
            days_stale=state["days_since_update"],
            subject=subj,
            body=email_body,
        )
        pid = orchestrator.pending.add(plan)
        return {
            "ok": True,
            "pending_id": pid,
            "label": plan.label,
            "recipient": state["owner_email"],
            "subject": subj,
            "body": email_body,
        }

    @router.get("/team-tracker/diff")
    async def team_tracker_diff():
        from ..tools.team_tracker import scan_team_progress
        scan = await asyncio.to_thread(scan_team_progress, settings=settings, audit=audit)
        return scan.get("diff", {})

    @router.post("/team-tracker/sync")
    async def team_tracker_sync(request: Request):
        if is_remote(request, settings):
            audit.log_action("team_sync", "POST /team-tracker/sync", "blocked_remote")
            raise HTTPException(403, "Syncing timeline baseline is blocked on remote sessions.")

        from ..tools.team_tracker import sync_timeline_with_gdrive
        sync_result = await asyncio.to_thread(
            sync_timeline_with_gdrive, settings=settings, audit=audit, pull_gdrive=True
        )
        count = sync_result.get("committed_count", 0)
        audit.log_action("team_sync", f"committed {count} baseline records", "ok")
        return sync_result

    @router.post("/team-tracker/open-excel")
    async def team_tracker_open_excel(request: Request):
        if is_remote(request, settings):
            audit.log_action("open_excel", "POST /team-tracker/open-excel", "blocked_remote")
            raise HTTPException(403, "Opening files is blocked on remote sessions.")

        from ..tools.file_navigator import get_allowed_roots, safe_open_file
        from ..tools.team_tracker import resolve_team_excel_path
        excel_path = resolve_team_excel_path(settings)
        if not excel_path or not excel_path.is_file():
            raise HTTPException(404, "Timeline Excel file not found on disk.")

        allowed_roots = list(get_allowed_roots(settings.desktop_root.parent))
        if excel_path.parent not in allowed_roots:
            allowed_roots.append(excel_path.parent)
        ok, msg = await asyncio.to_thread(safe_open_file, excel_path, allowed_roots)
        if not ok:
            raise HTTPException(500, msg)
        audit.log_action("open_excel", str(excel_path), "ok")
        return {"ok": True, "message": msg}

    return router
