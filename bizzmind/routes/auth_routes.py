"""Login / register / logout / me and organisation members."""

import db
import auth as sb_auth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bizzmind.config import log
from bizzmind.i18n import T, req_lang
from bizzmind.auth_middleware import _set_auth_cookies
from bizzmind import plans

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


# ------------------------------------------------------------------ account

class PasswordChange(BaseModel):
    password: str


class AccountPrefs(BaseModel):
    auto_recharge: bool


class BillingInfo(BaseModel):
    company: str = ""
    eik: str = ""           # company registration number (ЕИК/Bulstat)
    vat_id: str = ""        # VAT number
    mol: str = ""           # authorised representative
    address: str = ""
    city: str = ""
    country: str = ""
    invoice_email: str = ""


def _me_org():
    u = sb_auth.current_user()
    if not u:
        raise HTTPException(401)
    return u, (u.orgs[0] if u.orgs else None)


@router.get("/api/plans")
def public_plans():
    """Public: plan definitions for the pricing page (no auth, no org data)."""
    return {"plans": plans.PLANS, "packs": plans.PACKS, "costs": plans.COSTS}


@router.get("/api/account")
def account(request: Request):
    u, org = _me_org()
    st = plans.org_state(org) if org else {"plan": "free", "quota": 0, "extra": 0,
                                           "used": 0, "remaining": 0, "auto_recharge": False, "org_name": ""}
    return {
        "email": u.email,
        "org_name": st["org_name"],
        "role": u.roles.get(str(org), "member") if org else "member",
        "plan": st["plan"],
        "plans": plans.PLANS,
        "costs": plans.COSTS,
        "models": {k: {"label": v["label"], "min_plan": v["min_plan"]} for k, v in plans.MODELS.items()},
        "packs": plans.PACKS,
        "credits": {"quota": st["quota"], "extra": st["extra"], "used": st["used"],
                    "remaining": st["remaining"]},
        "auto_recharge": st["auto_recharge"],
        "projects_used": plans.project_count(org) if org else 0,
        "usage": plans.usage_breakdown(org) if org else [],
        "billing": _org_billing(org),
        "subscription": _org_subscription(org),
    }


def _org_subscription(org) -> dict | None:
    if org is None:
        return None
    with plans.pool().connection() as con:
        row = con.execute("SELECT paddle_customer_id, paddle_subscription_id, plan "
                          "FROM public.organizations WHERE id = %s", (org,)).fetchone()
    if not row or not row[1]:
        return None
    return {"customer_id": row[0], "subscription_id": row[1], "plan": row[2]}


@router.post("/api/account/portal")
def account_portal(request: Request):
    """Paddle customer portal session — manage subscription / payment method."""
    import json as _json
    import os
    import urllib.request
    u, org = _me_org()
    if org is None or not u.can_admin(org):
        raise HTTPException(403, T(req_lang(request), "forbidden"))
    with plans.pool().connection() as con:
        row = con.execute("SELECT paddle_customer_id FROM public.organizations WHERE id = %s",
                          (org,)).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "no billing customer")
    key = os.environ.get("PADDLE_API_KEY", "")
    base = "https://sandbox-api.paddle.com" if key.startswith("pdl_sdbx_") else "https://api.paddle.com"
    req = urllib.request.Request(f"{base}/customers/{row[0]}/portal-sessions", method="POST",
        data=b"{}", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = _json.loads(r.read())["data"]
    except Exception as e:
        log.info(f"paddle portal failed: {e}")
        raise HTTPException(502, "portal unavailable")
    urls = d.get("urls") or {}
    general = (urls.get("general") or {}).get("overview")
    return {"url": general}


def _org_billing(org) -> dict:
    if org is None:
        return {}
    with plans.pool().connection() as con:
        row = con.execute("SELECT billing FROM public.organizations WHERE id = %s", (org,)).fetchone()
    return row[0] if row and row[0] else {}


@router.post("/api/account/billing")
def account_billing(req: BillingInfo, request: Request):
    import json as _json
    u, org = _me_org()
    if org is None or not u.can_admin(org):
        raise HTTPException(403, T(req_lang(request), "forbidden"))
    with plans.pool().connection() as con:
        con.execute("UPDATE public.organizations SET billing = %s::jsonb WHERE id = %s",
                    (_json.dumps(req.model_dump()), org))
    log.info(f"account: billing details updated for org {org}")
    return {"ok": True}


@router.post("/api/account/password")
def account_password(req: PasswordChange, request: Request):
    u, _ = _me_org()
    lang = req_lang(request)
    if len(req.password) < 8:
        raise HTTPException(400, T(lang, "password_short"))
    try:
        sb_auth.admin_update_password(u.id, req.password)
    except sb_auth.AuthError as e:
        raise HTTPException(e.status, e.detail)
    log.info(f"account: password changed for {u.email}")
    return {"ok": True}


@router.post("/api/account/prefs")
def account_prefs(req: AccountPrefs, request: Request):
    u, org = _me_org()
    if org is None or not u.can_admin(org):
        raise HTTPException(403, T(req_lang(request), "forbidden"))
    with plans.pool().connection() as con:
        con.execute("UPDATE public.organizations SET auto_recharge = %s WHERE id = %s",
                    (req.auto_recharge, org))
    return {"ok": True, "auto_recharge": req.auto_recharge}
