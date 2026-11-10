"""Modular FastAPI routers package for Project Nightmare."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .auth import create_auth_router
from .chat import create_chat_router
from .database import create_database_router
from .defense import create_defense_router
from .deps import (
    COOKIE_NAME,
    DB_TOKEN_HEADER,
    FRONTEND_DIST,
    HELPER_FILE,
    LOCAL_HOSTS,
    ROOT_FILES,
    SETTINGS_TOKEN_HEADER,
    AppContext,
    PinAccess,
    SessionStore,
    check_host_and_origin,
    client_key,
    is_remote,
    make_guard,
)
from .router_review import create_router_review_router
from .settings import create_settings_router
from .system import create_system_router
from .team_tracker import create_team_tracker_router
from .telemetry import create_telemetry_router


def build_api_router(ctx: AppContext, guard) -> APIRouter:
    """Mounts all protected API sub-routers under a unified guard dependency."""
    api_router = APIRouter(dependencies=[Depends(guard)])
    api_router.include_router(create_system_router(ctx))
    api_router.include_router(create_chat_router(ctx))
    api_router.include_router(create_telemetry_router(ctx))
    api_router.include_router(create_defense_router(ctx))
    api_router.include_router(create_team_tracker_router(ctx))
    api_router.include_router(create_router_review_router(ctx))
    api_router.include_router(create_database_router(ctx))
    api_router.include_router(create_settings_router(ctx))
    return api_router


__all__ = [
    "AppContext",
    "COOKIE_NAME",
    "DB_TOKEN_HEADER",
    "FRONTEND_DIST",
    "HELPER_FILE",
    "LOCAL_HOSTS",
    "PinAccess",
    "ROOT_FILES",
    "SETTINGS_TOKEN_HEADER",
    "SessionStore",
    "build_api_router",
    "check_host_and_origin",
    "client_key",
    "create_auth_router",
    "is_remote",
    "make_guard",
]
