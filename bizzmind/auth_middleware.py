"""Supabase Auth via auth.py: httpOnly cookies with the Supabase access/refresh
tokens, verified per request (stateless — no sessions on disk/in memory)."""

import asyncio
import os
import time

import db
import auth as sb_auth
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse

from bizzmind.i18n import T, req_lang


PUBLIC_PATHS = ("/", "/login", "/api/auth/login", "/api/auth/logout", "/api/auth/register", "/api/cron/jobs", "/api/plans")
PUBLIC_PREFIXES = ("/static/", "/pub/")


def _set_auth_cookies(resp, tokens: dict):
    resp.set_cookie(sb_auth.ACCESS_COOKIE, tokens["access_token"], httponly=True, samesite="lax",
                    secure=os.environ.get("COOKIE_SECURE", "0") == "1", max_age=60 * 60 * 24 * 30)
    resp.set_cookie(sb_auth.REFRESH_COOKIE, tokens["refresh_token"], httponly=True, samesite="lax",
                    secure=os.environ.get("COOKIE_SECURE", "0") == "1", max_age=60 * 60 * 24 * 30)


# Supabase rotates refresh tokens: two parallel requests refreshing with the
# same token would race and the loser could kill the whole session family.
# Single-flight: one refresh per token, the result shared for a short window.
_refresh_lock = asyncio.Lock()
_refresh_cache: dict = {}          # refresh_token -> (tokens, at)


async def _refresh_shared(tok: str) -> dict:
    async with _refresh_lock:
        hit = _refresh_cache.get(tok)
        if hit and time.time() - hit[1] < 30:
            return hit[0]
        tokens = await run_in_threadpool(sb_auth.refresh, tok)
        _refresh_cache.clear()
        _refresh_cache[tok] = (tokens, time.time())
        return tokens


async def auth_middleware(request: Request, call_next):
    p = request.url.path
    if p in PUBLIC_PATHS or p.startswith(PUBLIC_PREFIXES):
        return await call_next(request)
    access = request.cookies.get(sb_auth.ACCESS_COOKIE)
    refresh_tok = request.cookies.get(sb_auth.REFRESH_COOKIE)
    user_json, new_tokens, session_dead = None, None, False
    try:
        if access:
            user_json = await run_in_threadpool(sb_auth.get_user, access)
        if user_json is None and refresh_tok:
            new_tokens = await _refresh_shared(refresh_tok)
            user_json = new_tokens.get("user") or await run_in_threadpool(sb_auth.get_user, new_tokens["access_token"])
    except sb_auth.AuthError as e:
        if e.status >= 500:
            return JSONResponse({"detail": e.detail}, status_code=503)
        user_json = None
        session_dead = True                     # the refresh itself was rejected
    if not user_json:
        if p.startswith("/api/"):
            resp = JSONResponse({"detail": T(req_lang(request), "not_logged_in")}, status_code=401)
        else:
            resp = RedirectResponse("/login")
        if session_dead or access or refresh_tok:
            # dead tokens must not stay in the browser — that is what caused
            # the endless refresh/redirect loop
            resp.delete_cookie(sb_auth.ACCESS_COOKIE)
            resp.delete_cookie(sb_auth.REFRESH_COOKIE)
        return resp
    user = await run_in_threadpool(sb_auth.load_memberships, db, user_json["id"], user_json.get("email", ""))
    token = sb_auth.set_current_user(user)
    try:
        resp = await call_next(request)
    finally:
        sb_auth._current.reset(token)
    if new_tokens:
        _set_auth_cookies(resp, new_tokens)
    return resp
