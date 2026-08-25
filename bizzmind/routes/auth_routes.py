"""Login / register / logout / me and organisation members."""

import db
import auth as sb_auth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bizzmind.config import log
from bizzmind.i18n import T, req_lang
from bizzmind.auth_middleware import _set_auth_cookies

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/api/auth/login")
def auth_login(req: LoginRequest, request: Request):
    try:
        tokens = sb_auth.sign_in(req.email, req.password)
    except sb_auth.AuthError as e:
        log.info(f"auth: failed login for '{req.email}' ({e.status})")
        if e.status >= 500:
            return JSONResponse({"detail": e.detail}, status_code=503)
        return JSONResponse({"detail": T(req_lang(request), "bad_credentials")}, status_code=401)
    email = (tokens.get("user") or {}).get("email", req.email.strip().lower())
    log.info(f"auth: '{email}' logged in")
    resp = JSONResponse({"ok": True, "email": email})
    _set_auth_cookies(resp, tokens)
    return resp


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    redirect: str = ""      # origin of the app the user registered from (confirmation link target)


@router.post("/api/auth/register")
def auth_register(req: RegisterRequest, request: Request):
    lang = req_lang(request)
    if len(req.password) < 8:
        return JSONResponse({"detail": T(lang, "password_short")}, status_code=400)
    try:
        redirect = req.redirect.strip() or (request.headers.get("origin") or "").rstrip("/")
        res = sb_auth.sign_up(req.email, req.password, req.name,
                              redirect_to=(redirect + "/login") if redirect.startswith("http") else None)
    except sb_auth.AuthError as e:
        log.info(f"auth: register failed for '{req.email}' ({e.status}: {e.detail})")
        if e.status == 422 or "already" in e.detail.lower():
            return JSONResponse({"detail": T(lang, "email_taken")}, status_code=409)
        return JSONResponse({"detail": e.detail}, status_code=400 if e.status < 500 else 503)
    log.info(f"auth: registered '{req.email}'")
    if res.get("access_token"):
        # confirmation disabled in Supabase -> signed in straight away
        resp = JSONResponse({"ok": True, "email": req.email.strip().lower(), "confirmed": True})
        _set_auth_cookies(resp, res)
        return resp
    return {"ok": True, "email": req.email.strip().lower(), "confirmed": False,
            "message": T(lang, "confirm_email")}


class InviteRequest(BaseModel):
    email: str
    role: str = "member"


@router.get("/api/org/members")
def org_members():
    u = sb_auth.current_user()
    org = u.orgs[0] if u and u.orgs else None
    if not org:
        raise HTTPException(404, "no organisation")
    return {"org_id": org, "members": sb_auth.org_members(db, org), "me": u.id}


@router.post("/api/org/invite")
def org_invite(req: InviteRequest, request: Request):
    """Admins invite colleagues: Supabase sends the invite email; on first login
    the invitee is attached to this organisation (pending_invites)."""
    u = sb_auth.current_user()
    org = u.orgs[0] if u and u.orgs else None
    lang = req_lang(request)
    if not org or not u.can_admin(org):
        raise HTTPException(403, T(lang, "forbidden"))
    if req.role not in ("admin", "member"):
        raise HTTPException(400, "bad role")
    email = req.email.strip().lower()
    try:
        invited = sb_auth.admin_invite(email, redirect_to=str(request.base_url).rstrip("/") + "/login")
    except sb_auth.AuthError as e:
        if e.status == 422 or "already" in e.detail.lower():
            # existing account -> attach directly
            match = [x for x in sb_auth.admin_list_users() if x.get("email") == email]
            if not match:
                raise HTTPException(400, e.detail)
            sb_auth.add_member(db, org, match[0]["id"], req.role)
            return {"ok": True, "attached": True}
        raise HTTPException(400 if e.status < 500 else 503, e.detail)
    sb_auth.add_member(db, org, invited["id"], req.role)
    log.info(f"auth: {u.email} invited {email} as {req.role}")
    return {"ok": True, "invited": True}


@router.delete("/api/org/members/{user_id}")
def org_remove(user_id: str, request: Request):
    u = sb_auth.current_user()
    org = u.orgs[0] if u and u.orgs else None
    if not org or not u.can_admin(org):
        raise HTTPException(403, T(req_lang(request), "forbidden"))
    if user_id == u.id:
        raise HTTPException(400, "cannot remove yourself")
    sb_auth.remove_member(db, org, user_id)
    return {"ok": True}


@router.post("/api/auth/logout")
def auth_logout(request: Request):
    access = request.cookies.get(sb_auth.ACCESS_COOKIE)
    if access:
        sb_auth.sign_out(access)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(sb_auth.ACCESS_COOKIE)
    resp.delete_cookie(sb_auth.REFRESH_COOKIE)
    log.info("auth: logged out")
    return resp


@router.get("/api/auth/me")
def auth_me(request: Request):
    u = sb_auth.current_user()
    if not u:
        return JSONResponse({"detail": "not logged in"}, status_code=401)
    return {"email": u.email, "id": u.id, "orgs": u.orgs, "roles": u.roles}
