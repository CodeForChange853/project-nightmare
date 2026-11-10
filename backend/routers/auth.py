"""Authentication router (/login and /logout)."""
from __future__ import annotations

import hmac
from fastapi import APIRouter, HTTPException, Request, Response

from .deps import (
    COOKIE_NAME,
    AppContext,
    LoginIn,
    check_host_and_origin,
    client_key,
    is_remote,
)


def create_auth_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    settings = ctx.settings
    sessions = ctx.sessions
    audit = ctx.audit

    @router.post("/login")
    async def login(body: LoginIn, request: Request, response: Response):
        check_host_and_origin(request, settings)
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
            secure=remote,
            path="/",
        )
        return {"ok": True, "role": role}

    @router.post("/logout")
    async def logout(request: Request, response: Response):
        check_host_and_origin(request, settings)
        sid = request.cookies.get(COOKIE_NAME, "")
        if sid:
            sessions.delete(sid)
        response.delete_cookie(key=COOKIE_NAME, path="/")
        return {"ok": True}

    return router
