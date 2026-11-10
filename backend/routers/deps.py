"""Shared dependencies, Pydantic schemas, session stores, and security guards for API routers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from ..config import BACKEND_DIR, Settings
from ..core.actions import Registry
from ..core.clearance import ClearanceManager
from ..core.llm import LLMProvider
from ..core.orchestrator import Orchestrator
from ..tools.audit import Audit

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
FORWARDED_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "tailscale-user-login")
COOKIE_NAME = "nightmare_session"
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
HELPER_FILE = BACKEND_DIR.parent / "nightmare_helper.txt"
ROOT_FILES = {"manifest.webmanifest": "application/manifest+json", "icon.svg": "image/svg+xml"}

DB_TOKEN_HEADER = "x-db-token"
SETTINGS_TOKEN_HEADER = "x-settings-token"


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ConfirmIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    approve: bool


class LoginIn(BaseModel):
    pin: str = Field(min_length=1, max_length=128)


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


@dataclass
class AppContext:
    """Shared runtime dependencies injected into modular API routers."""
    settings: Settings
    provider: LLMProvider
    registry: Registry
    audit: Audit
    clearance: ClearanceManager
    orchestrator: Orchestrator
    sessions: SessionStore
    db_access: PinAccess
    settings_access: PinAccess


def _hostname(host: str) -> str:
    host = host.strip().lower()
    name = host.split("]")[0].lstrip("[") if host.startswith("[") else host.rsplit(":", 1)[0]
    return name.rstrip(".")


def is_remote(request: Request, settings: Settings) -> bool:
    """True when the request came through `tailscale serve` (the phone), not this laptop's browser."""
    if _hostname(request.headers.get("host", "")) in settings.remote_hosts:
        return True
    return any(h in request.headers for h in FORWARDED_HEADERS)


def client_key(request: Request, settings: Settings) -> str:
    """Rate-limit key. Proxied requests use the last X-Forwarded-For entry appended by Tailscale."""
    if is_remote(request, settings):
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        return f"remote:{forwarded or 'unknown'}"
    return request.client.host if request.client else "local"


def check_host_and_origin(request: Request, settings: Settings) -> None:
    host = request.headers.get("host", "")
    hostname = _hostname(host)
    if is_remote(request, settings):
        if not settings.remote_hosts:
            raise HTTPException(403, "Remote access is off. Set NIGHTMARE_ALLOWED_HOSTS on the laptop.")
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_host is not None and _hostname(forwarded_host) not in settings.remote_hosts:
            raise HTTPException(403, "Bad host")
    if hostname not in LOCAL_HOSTS and hostname not in settings.remote_hosts:
        raise HTTPException(403, "Bad host")
    origin = request.headers.get("origin")
    if origin:
        same_host_http = {f"http://{host}".lower()} if hostname in LOCAL_HOSTS else set()
        remote_origins = {f"https://{h}" for h in settings.remote_hosts}
        allowed = {o.lower() for o in settings.allowed_origins} | same_host_http | remote_origins
        if origin.lower().rstrip("/") not in allowed:
            raise HTTPException(403, "Origin not allowed")


def make_guard(settings: Settings, sessions: SessionStore):
    async def guard(request: Request) -> None:
        check_host_and_origin(request, settings)
        remote = is_remote(request, settings)
        request.state.remote = remote
        supplied = request.headers.get("x-nightmare-token", "") or request.query_params.get("token", "")
        if supplied and hmac.compare_digest(supplied.encode(), settings.api_token.encode()):
            request.state.role = "readonly" if remote else "full"
            request.state.auth_mode = "token"
            request.state.memory_key = "token"
            return
        sid = request.cookies.get(COOKIE_NAME, "")
        role = sessions.get_role(sid)
        if role in {"full", "readonly"}:
            request.state.role = "readonly" if remote else role
            request.state.auth_mode = "session"
            request.state.memory_key = hashlib.sha256(sid.encode()).hexdigest()[:16]
            return
        raise HTTPException(401, "Authentication required")

    return guard


def require_full(request: Request) -> None:
    if getattr(request.state, "role", "full") == "readonly":
        raise HTTPException(403, "Only available in a laptop session, not a read-only one.")


def open_with_pin(body: LoginIn, request: Request, name: str, access: PinAccess, ctx: AppContext) -> dict:
    """Typed laptop PIN -> short-lived token for one panel. Rate-limited per device."""
    require_full(request)
    key = f"{name}:{client_key(request, ctx.settings)}"
    if not ctx.sessions.check_rate_limit(key):
        ctx.audit.log_action(f"{name}_open", key, "rate_limited")
        raise HTTPException(429, "Too many wrong PINs. Wait 60 seconds.")
    candidate = body.pin.strip().encode()
    expected = ctx.settings.pin or ctx.settings.api_token
    if not hmac.compare_digest(candidate, expected.encode()):
        ctx.sessions.record_failure(key)
        ctx.audit.log_action(f"{name}_open", key, "failed")
        raise HTTPException(403, "Wrong PIN.")
    ctx.sessions.clear_failures(key)
    ctx.audit.log_action(f"{name}_open", key, "ok")
    return {"ok": True, "token": access.open(), "expires_in": access.ttl}
