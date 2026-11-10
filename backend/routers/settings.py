"""Allowlisted applications and task settings router (/settings/*)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core import apps_config
from ..core.actions import ActionError, Registry
from ..tools.fs_reader import PathError, list_projects
from .deps import (
    SETTINGS_TOKEN_HEADER,
    AppContext,
    CheckIn,
    LoginIn,
    SettingsIn,
    open_with_pin,
    require_full,
)


def create_settings_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    settings = ctx.settings
    registry = ctx.registry
    orchestrator = ctx.orchestrator
    audit = ctx.audit
    settings_access = ctx.settings_access

    def require_settings(request: Request) -> None:
        require_full(request)
        if not settings_access.valid(request.headers.get(SETTINGS_TOKEN_HEADER, "")):
            raise HTTPException(403, "Settings are locked. Say “open settings” to unlock them again.")

    def read_apps_file() -> dict:
        try:
            return Registry.load(settings.apps_file).as_dict()
        except ActionError as exc:
            raise HTTPException(409, f"apps.json can't be read, fix it by hand first: {exc}")

    @router.post("/settings/open")
    async def settings_open(body: LoginIn, request: Request):
        return open_with_pin(body, request, "settings", settings_access, ctx)

    @router.post("/settings/close")
    async def settings_close(request: Request):
        settings_access.close(request.headers.get(SETTINGS_TOKEN_HEADER, ""))
        return {"ok": True}

    @router.get("/settings/apps")
    async def settings_apps(request: Request):
        require_settings(request)
        try:
            projects = [p.name for p in list_projects(settings.desktop_root)]
        except PathError:
            projects = []
        return {
            **read_apps_file(),
            "version": apps_config.file_version(settings.apps_file),
            "projects": projects,
            "shells": sorted(apps_config.SHELLS),
        }

    @router.post("/settings/apps")
    async def settings_save(body: SettingsIn, request: Request):
        require_settings(request)
        if body.version != apps_config.file_version(settings.apps_file):
            raise HTTPException(409, "apps.json was changed outside Settings. Reload to see the newest version.")
        current = read_apps_file()
        try:
            clean, notes = apps_config.validate(
                {"apps": body.apps, "tasks": body.tasks}, settings.desktop_root, current
            )
        except apps_config.ConfigError as exc:
            raise HTTPException(422, {"message": "Some entries need fixing.", "errors": exc.errors})
        changes = apps_config.describe_changes(current, clean)
        version = apps_config.file_version(settings.apps_file)
        if changes:
            version = apps_config.save(settings.apps_file, clean, settings.apps_file.parent / "backups")
            registry.replace(clean)
            orchestrator.pending.clear()
            audit.log_action("settings_save", "; ".join(changes)[:500], "ok")
        return {"ok": True, **clean, "version": version, "changes": changes, "notes": notes}

    @router.post("/settings/apps/check")
    async def settings_check(body: CheckIn, request: Request):
        require_settings(request)
        return apps_config.check_entry(body.kind, body.spec, settings.desktop_root)

    return router
