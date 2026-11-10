"""FastAPI application factory for Project Nightmare.

Bound to 127.0.0.1 by `python -m backend`; every API request must present the token
(or a valid session cookie), a local Host header (or a NIGHTMARE_ALLOWED_HOSTS name)
and, if sent, an allowed Origin. Requests arriving through `tailscale serve` (the phone)
are strictly read-only.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .core.actions import Registry
from .core.clearance import ClearanceManager
from .core.llm import AgyProvider, LLMProvider, NoLLMProvider
from .core.orchestrator import Orchestrator
from .routers import (
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
    build_api_router,
    check_host_and_origin,
    client_key,
    create_auth_router,
    is_remote,
    make_guard,
)
from .tools.audit import Audit
from .tools.email_listener import email_event_dispatcher


def create_app(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    dist_dir: Path | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if provider is None:
        provider = (
            AgyProvider(
                settings.agy_command,
                settings.agy_timeout,
                settings.agy_format,
                fast_model=settings.agy_fast_model,
                smart_model=settings.agy_smart_model,
            )
            if settings.llm_enabled
            else NoLLMProvider()
        )
    registry = Registry.load(settings.apps_file)
    audit = Audit(settings.db_path)
    audit.prune_actions(settings.log_retention_days)
    audit.prune_conversations(settings.log_retention_days)
    clearance = ClearanceManager()
    orchestrator = Orchestrator(
        settings,
        provider,
        registry,
        audit,
        clearance=clearance,
        event_emitter=email_event_dispatcher.dispatch,
    )
    sessions = SessionStore(ttl=settings.session_ttl)
    db_access = PinAccess()
    settings_access = PinAccess()
    guard = make_guard(settings, sessions)

    ctx = AppContext(
        settings=settings,
        provider=provider,
        registry=registry,
        audit=audit,
        clearance=clearance,
        orchestrator=orchestrator,
        sessions=sessions,
        db_access=db_access,
        settings_access=settings_access,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        email_event_dispatcher.set_loop(asyncio.get_running_loop())
        task = None
        warmup_task = None
        file_index_task = None
        weather_task = None
        github_task = None
        subscriber = None
        streaming_pull_future = None

        try:
            from .core.semantic_router import warmup_semantic_router
            warmup_task = asyncio.create_task(asyncio.to_thread(warmup_semantic_router))
        except Exception:
            pass

        try:
            from .tools.file_navigator import get_allowed_roots, index_files
            allowed_roots = get_allowed_roots(settings.desktop_root.parent)
            file_index_task = asyncio.create_task(asyncio.to_thread(index_files, allowed_roots, audit))
        except Exception:
            pass

        try:
            from .tools.weather import run_weather_prefetcher
            weather_task = asyncio.create_task(
                run_weather_prefetcher(settings.weather_city, settings.weather_api_key, 3600)
            )
        except Exception:
            pass

        try:
            from .tools.workspace import run_github_cache_refresher
            github_task = asyncio.create_task(run_github_cache_refresher(settings.desktop_root, 600))
        except Exception:
            pass

        if settings.summary_refresh_sec > 0:
            task = asyncio.create_task(orchestrator.run_summary_refresher(settings.summary_refresh_sec))

        if not os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("NIGHTMARE_TESTING"):
            try:
                from google.cloud import pubsub_v1
                from .tools.email_listener import process_email_message

                project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "project-nightmare-512605")
                subscription_id = "nightmare-local-sub"
                subscriber = pubsub_v1.SubscriberClient()
                subscription_path = subscriber.subscription_path(project_id, subscription_id)
                streaming_pull_future = subscriber.subscribe(
                    subscription_path,
                    callback=process_email_message,
                )
                logging.getLogger("nightmare").info(f"Pub/Sub listener active on {subscription_id}.")
            except Exception as e:
                logging.getLogger("nightmare").error(f"Failed to start Pub/Sub listener: {e}")

        try:
            yield
        finally:
            for bg_task in (task, warmup_task, file_index_task, weather_task, github_task):
                if bg_task is not None and not bg_task.done():
                    bg_task.cancel()

            if streaming_pull_future is not None:
                streaming_pull_future.cancel()
                try:
                    streaming_pull_future.result(timeout=5)
                except Exception:
                    pass
            if subscriber is not None:
                subscriber.close()

    app = FastAPI(title="Project Nightmare", lifespan=lifespan)
    app.state.ctx = ctx
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Nightmare-Token", "X-DB-Token", "X-Settings-Token"],
    )

    auth_router = create_auth_router(ctx)
    api_router = build_api_router(ctx, guard)

    # Mount routes both at root (for Vite proxy / tests) and under /api (for single-server mode)
    app.include_router(auth_router)
    app.include_router(auth_router, prefix="/api")
    app.include_router(api_router)
    app.include_router(api_router, prefix="/api")

    ui_dir = Path(dist_dir) if dist_dir is not None else FRONTEND_DIST
    index_html = ui_dir / "index.html"
    if index_html.is_file():
        assets_dir = ui_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/", include_in_schema=False)
        async def serve_index(request: Request):
            check_host_and_origin(request, settings)
            return FileResponse(index_html)

        def root_file(path: Path, media_type: str):
            async def serve() -> FileResponse:
                return FileResponse(path, media_type=media_type)

            return serve

        for name, media_type in ROOT_FILES.items():
            if (ui_dir / name).is_file():
                app.add_api_route(f"/{name}", root_file(ui_dir / name, media_type), include_in_schema=False)

    return app
