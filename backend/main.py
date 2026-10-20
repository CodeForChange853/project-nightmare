"""FastAPI app. Bound to 127.0.0.1 by `python -m backend`; every API request must present the token
(or a valid session cookie), a local Host header (or a NIGHTMARE_ALLOWED_HOSTS name) and, if sent, an
allowed Origin. Requests arriving through `tailscale serve` (the phone) are always read-only."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BACKEND_DIR, Settings
from .core import apps_config
from .core.actions import ActionError, Registry
from .core.llm import AgyProvider, LLMProvider, NoLLMProvider
from .core.orchestrator import Orchestrator
from .tools.audit import Audit
from .tools.fs_reader import PathError, list_projects, project_cards

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
FORWARDED_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "tailscale-user-login")
COOKIE_NAME = "nightmare_session"
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
HELPER_FILE = BACKEND_DIR.parent / "nightmare_helper.txt"
# files from frontend/public that sit at the dist root (home-screen install); nothing else there is served
ROOT_FILES = {"manifest.webmanifest": "application/manifest+json", "icon.svg": "image/svg+xml"}


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ConfirmIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    approve: bool


class LoginIn(BaseModel):
    pin: str = Field(min_length=1, max_length=128)


DB_TOKEN_HEADER = "x-db-token"
SETTINGS_TOKEN_HEADER = "x-settings-token"


class SettingsIn(BaseModel):
    apps: dict
    tasks: dict
    version: str = Field(min_length=1, max_length=64)


class CheckIn(BaseModel):
    kind: Literal["app", "task"]
    spec: dict


class PinAccess:
    """Short-lived tokens for the database viewer and Settings, issued after the PIN is typed (never spoken)."""

    def __init__(self, ttl: int = 600):
        self.ttl = ttl
        self._tokens: dict[str, float] = {}  # token -> monotonic expiry

    def open(self) -> str:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = time.monotonic() + self.ttl
        return token

    def valid(self, token: str) -> bool:
        expires = self._tokens.get(token or "")
        if expires is None:
            return False
        if time.monotonic() > expires:
            self._tokens.pop(token, None)
            return False
        return True

    def close(self, token: str) -> None:
        self._tokens.pop(token or "", None)


class SessionStore:
    """In-memory session store with per-IP login rate limiting."""

    def __init__(self, ttl: int = 86400 * 7, max_failures: int = 5, window_sec: int = 60):
        self.ttl = ttl
        self.max_failures = max_failures
        self.window_sec = window_sec
        self._sessions: dict[str, tuple[str, float]] = {}  # sid -> (role, expires_at)
        self._failures: dict[str, list[float]] = {}  # ip -> [monotonic_ts]

    def check_rate_limit(self, key: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_sec]
        self._failures[key] = recent
        return len(recent) < self.max_failures

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_sec]
        recent.append(now)
        self._failures[key] = recent

    def clear_failures(self, key: str) -> None:
        self._failures.pop(key, None)

    def create(self, role: str) -> str:
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = (role, time.monotonic() + self.ttl)
        return sid

    def get_role(self, sid: str) -> str | None:
        if not sid:
            return None
        entry = self._sessions.get(sid)
        if not entry:
            return None
        role, expires_at = entry
        if time.monotonic() > expires_at:
            self._sessions.pop(sid, None)
            return None
        return role

    def delete(self, sid: str) -> None:
        self._sessions.pop(sid, None)


def _hostname(host: str) -> str:
    host = host.strip().lower()
    name = host.split("]")[0].lstrip("[") if host.startswith("[") else host.rsplit(":", 1)[0]
    return name.rstrip(".")


def is_remote(request: Request, settings: Settings) -> bool:
    """True when the request came through `tailscale serve` (the phone), not this laptop's browser.
    The server only listens on 127.0.0.1, so remote traffic always arrives via that proxy, which
    adds X-Forwarded-* headers. Neither the browser nor the Vite dev proxy sends them."""
    if _hostname(request.headers.get("host", "")) in settings.remote_hosts:
        return True
    return any(h in request.headers for h in FORWARDED_HEADERS)


def client_key(request: Request, settings: Settings) -> str:
    """Rate-limit key. Proxied requests all come from 127.0.0.1, so use the address tailscale
    appended (the last X-Forwarded-For entry; earlier ones are whatever the client sent)."""
    if is_remote(request, settings):
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        return f"remote:{forwarded or 'unknown'}"
    return request.client.host if request.client else "local"


def _check_host_and_origin(request: Request, settings: Settings) -> None:
    host = request.headers.get("host", "")
    hostname = _hostname(host)
    if is_remote(request, settings):
        if not settings.remote_hosts:  # fail closed until NIGHTMARE_ALLOWED_HOSTS is set
            raise HTTPException(403, "Remote access is off. Set NIGHTMARE_ALLOWED_HOSTS on the laptop.")
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_host is not None and _hostname(forwarded_host) not in settings.remote_hosts:
            raise HTTPException(403, "Bad host")
    if hostname not in LOCAL_HOSTS and hostname not in settings.remote_hosts:  # blocks DNS-rebinding
        raise HTTPException(403, "Bad host")
    origin = request.headers.get("origin")
    if origin:
        # plain http only for the laptop itself; the tailnet name is served over https only
        same_host_http = {f"http://{host}".lower()} if hostname in LOCAL_HOSTS else set()
        remote_origins = {f"https://{h}" for h in settings.remote_hosts}
        allowed = {o.lower() for o in settings.allowed_origins} | same_host_http | remote_origins
        if origin.lower().rstrip("/") not in allowed:  # blocks other web pages
            raise HTTPException(403, "Origin not allowed")


def make_guard(settings: Settings, sessions: SessionStore):
    async def guard(request: Request) -> None:
        _check_host_and_origin(request, settings)
        remote = is_remote(request, settings)
        request.state.remote = remote
        supplied = request.headers.get("x-nightmare-token", "")
        if supplied and hmac.compare_digest(supplied.encode(), settings.api_token.encode()):
            request.state.role = "readonly" if remote else "full"
            request.state.auth_mode = "token"
            request.state.memory_key = "token"
            return
        sid = request.cookies.get(COOKIE_NAME, "")
        role = sessions.get_role(sid)
        if role in {"full", "readonly"}:
            request.state.role = "readonly" if remote else role  # the phone never acts, whatever the PIN
            request.state.auth_mode = "session"
            # conversation memory is kept per login; keyed by a hash so the cookie itself isn't reused
            request.state.memory_key = hashlib.sha256(sid.encode()).hexdigest()[:16]
            return
        raise HTTPException(401, "Authentication required")

    return guard


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
    orchestrator = Orchestrator(settings, provider, registry, audit)
    sessions = SessionStore(ttl=settings.session_ttl)
    db_access = PinAccess()
    settings_access = PinAccess()
    guard = make_guard(settings, sessions)

    app = FastAPI(title="Project Nightmare")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Nightmare-Token", "X-DB-Token", "X-Settings-Token"],
    )

    auth_router = APIRouter()

    @auth_router.post("/login")
    async def login(body: LoginIn, request: Request, response: Response):
        _check_host_and_origin(request, settings)
        key = client_key(request, settings)
        if not sessions.check_rate_limit(key):
            audit.log_action("login", key, "rate_limited")
            raise HTTPException(429, "Too many failed PIN attempts. Wait 60 seconds.")

        candidate = body.pin.strip()
        role = None
        if settings.pin and hmac.compare_digest(candidate.encode(), settings.pin.encode()):
            role = "full"
        elif settings.phone_pin and hmac.compare_digest(candidate.encode(), settings.phone_pin.encode()):
            role = "readonly"
        elif hmac.compare_digest(candidate.encode(), settings.api_token.encode()):
            role = "full"

        if role is None:
            sessions.record_failure(key)
            audit.log_action("login", key, "failed")
            raise HTTPException(401, "Invalid PIN")

        remote = is_remote(request, settings)
        if remote:
            role = "readonly"
        sessions.clear_failures(key)
        sid = sessions.create(role)
        audit.log_action("login", f"{key} ({role})", "ok")
        response.set_cookie(
            key=COOKIE_NAME,
            value=sid,
            max_age=settings.session_ttl,
            httponly=True,
            samesite="strict",
            secure=remote,  # tailscale serve is HTTPS; the laptop itself uses plain http://127.0.0.1
            path="/",
        )
        return {"ok": True, "role": role}

    @auth_router.post("/logout")
    async def logout(request: Request, response: Response):
        _check_host_and_origin(request, settings)
        sid = request.cookies.get(COOKIE_NAME, "")
        if sid:
            sessions.delete(sid)
        response.delete_cookie(key=COOKIE_NAME, path="/")
        return {"ok": True}

    api_router = APIRouter(dependencies=[Depends(guard)])

    @api_router.get("/status")
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
        return {
            "ok": True,
            "role": getattr(request.state, "role", "full"),
            "auth_mode": getattr(request.state, "auth_mode", "token"),
            "remote": getattr(request.state, "remote", False),
            "llm": provider.name,
            "desktop_root": str(settings.desktop_root),
            "projects": projects,
            "project_cards": cards,
            "notes": audit.list_notes(),
            "apps": sorted(registry.apps),
            "tasks": sorted(registry.tasks),
            "raw_commands": settings.allow_raw_commands,
            "llm_calls": audit.llm_counts(),
        }

    @api_router.post("/chat")
    async def chat(body: ChatIn, request: Request):
        readonly = getattr(request.state, "role", "full") == "readonly"
        session = getattr(request.state, "memory_key", "default")
        return (await orchestrator.handle(body.text, readonly=readonly, session=session)).to_dict()

    @api_router.post("/session/reset")
    async def session_reset(request: Request):
        """/clear and /new: forget this login's conversation so the next message starts fresh."""
        orchestrator.reset_session(getattr(request.state, "memory_key", "default"))
        return {"ok": True}

    @api_router.get("/help")
    async def help_text():
        """The command list shown by /help, read straight from nightmare_helper.txt."""
        try:
            return {"text": HELPER_FILE.read_text(encoding="utf-8")}
        except OSError:
            raise HTTPException(404, "nightmare_helper.txt is missing from the project folder.")

    @api_router.post("/confirm")
    async def confirm(body: ConfirmIn, request: Request):
        if getattr(request.state, "role", "full") == "readonly":
            audit.log_action("confirm", body.id, "blocked_readonly")
            raise HTTPException(403, "Read-only session cannot approve actions")
        return (await orchestrator.confirm(body.id, body.approve)).to_dict()

    @api_router.get("/audit")
    async def recent():
        return {"actions": audit.recent_actions()}

    # ---- database viewer: "database access open" -> PIN -> records; "database close" ----

    def require_full(request: Request) -> None:
        if getattr(request.state, "role", "full") == "readonly":
            raise HTTPException(403, "Only available in a laptop session, not a read-only one.")

    def require_db(request: Request) -> None:
        require_full(request)
        # 403, not 401: a closed database must not look like a logged-out session to the UI
        if not db_access.valid(request.headers.get(DB_TOKEN_HEADER, "")):
            raise HTTPException(403, "The database is closed. Say “database access open” to open it again.")

    def open_with_pin(body: LoginIn, request: Request, name: str, access: PinAccess) -> dict:
        """Typed laptop PIN -> short-lived token for one panel. Rate-limited per device."""
        require_full(request)
        key = f"{name}:{client_key(request, settings)}"
        if not sessions.check_rate_limit(key):
            audit.log_action(f"{name}_open", key, "rate_limited")
            raise HTTPException(429, "Too many wrong PINs. Wait 60 seconds.")
        candidate = body.pin.strip().encode()
        expected = settings.pin or settings.api_token  # no PIN configured: the token is the secret
        if not hmac.compare_digest(candidate, expected.encode()):
            sessions.record_failure(key)
            audit.log_action(f"{name}_open", key, "failed")
            raise HTTPException(403, "Wrong PIN.")
        sessions.clear_failures(key)
        audit.log_action(f"{name}_open", key, "ok")
        return {"ok": True, "token": access.open(), "expires_in": access.ttl}

    @api_router.post("/db/open")
    async def db_open(body: LoginIn, request: Request):
        return open_with_pin(body, request, "db", db_access)

    @api_router.post("/db/close")
    async def db_close(request: Request):
        db_access.close(request.headers.get(DB_TOKEN_HEADER, ""))
        audit.log_action("db_close", "viewer", "ok")
        return {"ok": True}

    @api_router.get("/db/records")
    async def db_records(request: Request):
        require_db(request)
        return {
            "counts": audit.table_counts(),
            "notes": audit.list_notes(include_done=True),
            "actions": audit.recent_actions(limit=200),
            "llm_calls": audit.recent_llm_calls(limit=200),
        }

    @api_router.post("/db/notes/{note_id}/delete")
    async def db_delete_note(note_id: int, request: Request):
        require_db(request)
        deleted = audit.delete_note(note_id)
        if deleted is None:
            raise HTTPException(404, "That reminder no longer exists.")
        audit.log_action("delete_note", f"#{note_id} (database viewer)", "ok")
        return {"ok": True, "deleted": deleted}

    # ---- Settings: "open settings" -> PIN -> edit apps.json (laptop only, never by voice) ----

    def require_settings(request: Request) -> None:
        require_full(request)
        if not settings_access.valid(request.headers.get(SETTINGS_TOKEN_HEADER, "")):
            raise HTTPException(403, "Settings are locked. Say “open settings” to unlock them again.")

    def read_apps_file() -> dict:
        try:
            return Registry.load(settings.apps_file).as_dict()
        except ActionError as exc:
            raise HTTPException(409, f"apps.json can't be read, fix it by hand first: {exc}")

    @api_router.post("/settings/open")
    async def settings_open(body: LoginIn, request: Request):
        return open_with_pin(body, request, "settings", settings_access)

    @api_router.post("/settings/close")
    async def settings_close(request: Request):
        settings_access.close(request.headers.get(SETTINGS_TOKEN_HEADER, ""))
        return {"ok": True}

    @api_router.get("/settings/apps")
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
        }

    @api_router.post("/settings/apps")
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
            orchestrator.pending.clear()  # a waiting confirmation may describe the old entry
            audit.log_action("settings_save", "; ".join(changes)[:500], "ok")
        return {"ok": True, **clean, "version": version, "changes": changes, "notes": notes}

    @api_router.post("/settings/apps/check")
    async def settings_check(body: CheckIn, request: Request):
        require_settings(request)
        return apps_config.check_entry(body.kind, body.spec, settings.desktop_root)

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
            _check_host_and_origin(request, settings)
            return FileResponse(index_html)

        def root_file(path: Path, media_type: str):
            async def serve() -> FileResponse:  # no parameters, so nothing in the URL can pick the file
                return FileResponse(path, media_type=media_type)

            return serve

        for name, media_type in ROOT_FILES.items():
            if (ui_dir / name).is_file():
                app.add_api_route(f"/{name}", root_file(ui_dir / name, media_type), include_in_schema=False)

    return app
