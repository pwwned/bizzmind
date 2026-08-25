"""Supabase Auth via auth.py: httpOnly cookies with the Supabase access/refresh
tokens, verified per request (stateless — no sessions on disk/in memory)."""

import os

import db
import auth as sb_auth
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse

from bizzmind.i18n import T, req_lang


PUBLIC_PATHS = ("/", "/login", "/api/auth/login", "/api/auth/logout", "/api/auth/register", "/api/cron/jobs", "/api/_debug/request")
PUBLIC_PREFIXES = ("/static/", "/pub/")


def _set_auth_cookies(resp, tokens: dict):
    resp.set_cookie(sb_auth.ACCESS_COOKIE, tokens["access_token"], httponly=True, samesite="lax",
                    secure=os.environ.get("COOKIE_SECURE", "0") == "1", max_age=60 * 60 * 24 * 30)
    resp.set_cookie(sb_auth.REFRESH_COOKIE, tokens["refresh_token"], httponly=True, samesite="lax",
                    secure=os.environ.get("COOKIE_SECURE", "0") == "1", max_age=60 * 60 * 24 * 30)


async def auth_middleware(request: Request, call_next):
    p = request.url.path
    if p in PUBLIC_PATHS or p.startswith(PUBLIC_PREFIXES):
        return await call_next(request)
    access = request.cookies.get(sb_auth.ACCESS_COOKIE)
    refresh_tok = request.cookies.get(sb_auth.REFRESH_COOKIE)
    user_json, new_tokens = None, None
    try:
        if access:
            user_json = await run_in_threadpool(sb_auth.get_user, access)
        if user_json is None and refresh_tok:
            new_tokens = await run_in_threadpool(sb_auth.refresh, refresh_tok)
            user_json = new_tokens.get("user") or await run_in_threadpool(sb_auth.get_user, new_tokens["access_token"])
    except sb_auth.AuthError as e:
        if e.status >= 500:
            return JSONResponse({"detail": e.detail}, status_code=503)
        user_json = None
    if not user_json:
        if p.startswith("/api/"):
            return JSONResponse({"detail": T(req_lang(request), "not_logged_in")}, status_code=401)
        return RedirectResponse("/login")
    user = await run_in_threadpool(sb_auth.load_memberships, db, user_json["id"], user_json.get("email", ""))
    token = sb_auth.set_current_user(user)
    try:
        resp = await call_next(request)
    finally:
        sb_auth._current.reset(token)
    if new_tokens:
        _set_auth_cookies(resp, new_tokens)
    return resp
