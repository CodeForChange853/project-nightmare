"""System status, Level 5 clearance status, live weather, and desktop window mode router."""
from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Request

from ..tools.fs_reader import PathError, project_cards
from .deps import AppContext, is_remote


def create_system_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    settings = ctx.settings
    provider = ctx.provider
    registry = ctx.registry
    audit = ctx.audit
    clearance = ctx.clearance
    orchestrator = ctx.orchestrator

    @router.get("/status")
    async def status(request: Request):
        try:
            cards = project_cards(
                settings.desktop_root,
                settings.handoff_filename,
                orchestrator._summary_cache,
            )
            projects = [c["name"] for c in cards]
        except PathError:
            cards = []
            projects = []
        session_key = getattr(request.state, "memory_key", "default")
        remote = getattr(request.state, "remote", False) or is_remote(request, settings)
        clear_lvl = clearance.get_level(session_key, is_remote=remote)

        telemetry_snap = None
        try:
            from ..tools.system_telemetry import get_memory_status, get_power_status
            pwr = get_power_status()
            mem = get_memory_status()
            telemetry_snap = {
                "battery_pct": pwr.get("battery_pct"),
                "battery_status": pwr.get("status"),
                "ram_pct": mem.get("memory_load_pct"),
                "ram_used_gb": mem.get("used_phys_gb"),
                "ram_total_gb": mem.get("total_phys_gb"),
            }
        except Exception:
            pass

        defense_snap = None
        try:
            defense_snap = orchestrator.defense_copilot.get_pacing_status()
        except Exception:
            pass

        weather_card = None
        try:
            from ..tools.weather import get_cached_weather_card
            weather_card = get_cached_weather_card(settings.weather_city)
        except Exception:
            pass

        recent_files = []
        try:
            recent_files = audit.list_recent_files(4)
        except Exception:
            pass

        recent_apps = []
        try:
            recent_apps = audit.list_recent_apps(registry.apps, 4)
        except Exception:
            pass

        return {
            "ok": True,
            "role": getattr(request.state, "role", "full"),
            "auth_mode": getattr(request.state, "auth_mode", "token"),
            "remote": getattr(request.state, "remote", False),
            "clearance_level": clear_lvl,
            "clearance_label": clearance.get_label(clear_lvl),
            "clearance_expires_in": clearance.get_remaining_seconds(session_key, is_remote=remote),
            "clearance_timeout": clearance.get_timeout_seconds(clear_lvl),
            "telemetry": telemetry_snap,
            "defense": defense_snap,
            "weather_card": weather_card,
            "recent_files": recent_files,
            "recent_apps": recent_apps,
            "llm": provider.name,
            "desktop_root": str(settings.desktop_root),
            "projects": projects,
            "project_cards": cards,
            "notes": audit.list_notes(),
            "calendar_events": audit.list_calendar_events(),
            "measurable_tasks": audit.list_measurable_tasks(),
            "apps": sorted(registry.apps),
            "tasks": sorted(registry.tasks),
            "raw_commands": settings.allow_raw_commands,
            "llm_calls": audit.llm_counts(),
        }

    @router.get("/clearance/status")
    async def clearance_status(request: Request):
        session_key = getattr(request.state, "memory_key", "default")
        remote = is_remote(request, settings)
        lvl = clearance.get_level(session_key, is_remote=remote)
        return {
            "ok": True,
            "level": lvl,
            "label": clearance.get_label(lvl),
            "expires_in": None,
            "timeout": None,
        }

    @router.get("/weather")
    async def live_weather(city: str | None = None, force: bool = False):
        from ..tools.weather import WeatherError, fetch_weather_card
        target_city = (city or settings.weather_city or "Calbayog").strip()
        try:
            card = await fetch_weather_card(target_city, api_key=settings.weather_api_key, force=force)
            return {"ok": True, "weather": card}
        except WeatherError as exc:
            raise HTTPException(502, str(exc))

    @router.post("/window/mode")
    async def set_window_mode(body: dict, request: Request):
        if is_remote(request, settings) or getattr(request.state, "role", "full") == "readonly":
            raise HTTPException(403, "Window controls are only available on the local desktop session.")
        mode = str(body.get("mode", "")).lower().strip()
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                u = ctypes.WinDLL("user32", use_last_error=True)
                u.GetForegroundWindow.restype = wintypes.HWND
                hwnd = u.GetForegroundWindow()
                if hwnd:
                    if mode == "mini":
                        u.ShowWindow(hwnd, 9)  # SW_RESTORE
                        rect = wintypes.RECT()
                        u.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)
                        w, h = 420, 580
                        x = max(rect.left, rect.right - w - 16)
                        y = max(rect.top, rect.bottom - h - 16)
                        u.SetWindowPos(hwnd, -1, x, y, w, h, 0x0040)
                    elif mode == "maximize":
                        u.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
                        u.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                    elif mode == "restore":
                        u.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
                        u.ShowWindow(hwnd, 9)  # SW_RESTORE
            except Exception:
                pass
        return {"ok": True, "mode": mode}

    return router
