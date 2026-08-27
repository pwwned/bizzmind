"""Bizzmind — authentication on Supabase Auth (GoTrue).

Stateless by design so it works on serverless: the browser holds the Supabase
access/refresh tokens in httpOnly cookies set by our API; every request is
verified against Supabase (`GET /auth/v1/user`) with a short in-process cache,
and expired access tokens are refreshed transparently. No sessions on disk or
in memory, no password handling of our own.

Tenancy: every user belongs to one or more organisations (public.memberships).
On first login a personal organisation is created and the user becomes its
owner. `current_user()` exposes the user and their org ids to request handlers
via a contextvar set in the middleware.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger("studio")

ACCESS_COOKIE = "sb_access"
REFRESH_COOKIE = "sb_refresh"
_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, dict]] = {}


def _url() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/")


def _anon() -> str:
    return os.environ["SUPABASE_ANON_KEY"]


def _service() -> str:
    return os.environ["SUPABASE_SERVICE_KEY"]


def enabled() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"))


@dataclass
class User:
    id: str
    email: str
    orgs: list[str] = field(default_factory=list)      # org ids the user belongs to
    roles: dict[str, str] = field(default_factory=dict)  # org id -> role

    def can_read(self, org_id) -> bool:
        return org_id is not None and str(org_id) in self.orgs

    def can_admin(self, org_id) -> bool:
        return self.roles.get(str(org_id)) in ("owner", "admin")


_current: contextvars.ContextVar[User | None] = contextvars.ContextVar("current_user", default=None)


def current_user() -> User | None:
    return _current.get()


def set_current_user(u: User | None):
    return _current.set(u)


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


# --------------------------------------------------------------- GoTrue calls

def _call(method: str, path: str, body: dict | None = None, token: str | None = None,
          service: bool = False) -> dict:
    key = _service() if service else _anon()
    req = urllib.request.Request(
        _url() + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"apikey": key, "Authorization": f"Bearer {token or key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = {}
        msg = detail.get("msg") or detail.get("error_description") or detail.get("message") or detail.get("error") or str(e)
        raise AuthError(e.code, msg)
    except Exception as e:
        raise AuthError(503, f"auth unavailable: {e}")


def sign_in(email: str, password: str) -> dict:
    """-> {access_token, refresh_token, expires_in, user}"""
    return _call("POST", "/auth/v1/token?grant_type=password",
                 {"email": email.strip().lower(), "password": password})


def sign_up(email: str, password: str, name: str = "", redirect_to: str | None = None) -> dict:
    """Self-service registration. With email confirmation enabled in Supabase the
    response has no session (user must confirm first). `redirect_to` is where the
    confirmation link lands — must be in Supabase Auth "Redirect URLs"."""
    body = {"email": email.strip().lower(), "password": password}
    if name:
        body["data"] = {"full_name": name}
    path = "/auth/v1/signup" + (f"?redirect_to={urllib.parse.quote(redirect_to, safe='')}" if redirect_to else "")
    return _call("POST", path, body)


def admin_invite(email: str, redirect_to: str | None = None) -> dict:
    """Send a Supabase invite email (user sets the password from the link)."""
    body = {"email": email.strip().lower()}
    path = "/auth/v1/invite" + (f"?redirect_to={redirect_to}" if redirect_to else "")
    return _call("POST", path, body, service=True)


def refresh(refresh_token: str) -> dict:
    return _call("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": refresh_token})


def sign_out(access_token: str) -> None:
    try:
        _call("POST", "/auth/v1/logout", {}, token=access_token)
    except AuthError:
        pass


_jwks_client = None


def _verify_locally(access_token: str) -> dict | None:
    """Validate the Supabase JWT with the project's public keys (JWKS, ES256) —
    no network round trip per request. Returns {id, email} or None."""
    global _jwks_client
    try:
        import jwt
        from jwt import PyJWKClient
        if _jwks_client is None:
            _jwks_client = PyJWKClient(_url() + "/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)
        key = _jwks_client.get_signing_key_from_jwt(access_token).key
        claims = jwt.decode(access_token, key, algorithms=["ES256", "RS256"], audience="authenticated",
                            options={"require": ["exp", "sub"]})
        return {"id": claims["sub"], "email": claims.get("email", ""), "role": claims.get("role")}
    except Exception as e:  # expired, bad signature, HS256 legacy project, JWKS unreachable…
        if "expired" in str(e).lower():
            return None
        log.info(f"auth: local JWT verification unavailable ({type(e).__name__}) — falling back to GoTrue")
        raise


def get_user(access_token: str) -> dict | None:
    """Verified user for an access token (cached briefly). None if invalid/expired."""
    h = hashlib.sha256(access_token.encode()).hexdigest()
    hit = _cache.get(h)
    now = time.time()
    if hit and hit[0] > now:
        return hit[1]
    try:
        u = _verify_locally(access_token)
        if u is None:
            return None
    except Exception:
        try:
            u = _call("GET", "/auth/v1/user", token=access_token)
        except AuthError as e:
            if e.status in (401, 403):
                return None
            raise
    _cache[h] = (now + _CACHE_TTL, u)
    if len(_cache) > 5000:
        for k in [k for k, v in _cache.items() if v[0] <= now][:2500]:
            _cache.pop(k, None)
    return u


def admin_update_password(user_id: str, password: str) -> dict:
    return _call("PUT", f"/auth/v1/admin/users/{user_id}", {"password": password}, service=True)


def admin_create_user(email: str, password: str, confirm: bool = True) -> dict:
    return _call("POST", "/auth/v1/admin/users",
                 {"email": email.strip().lower(), "password": password, "email_confirm": confirm},
                 service=True)


def admin_list_users() -> list[dict]:
    return _call("GET", "/auth/v1/admin/users?per_page=200", service=True).get("users", [])


# --------------------------------------------------------------- membership (Postgres)

def org_members(db, org_id: str) -> list[dict]:
    with db.pool().connection() as con:
        rows = con.execute(
            "SELECT m.user_id, m.role, m.created_at, u.email FROM public.memberships m "
            "JOIN auth.users u ON u.id = m.user_id WHERE m.org_id = %s ORDER BY m.created_at", (org_id,)).fetchall()
    return [{"user_id": str(r[0]), "role": r[1], "since": r[2].strftime("%Y-%m-%d"), "email": r[3]} for r in rows]


def add_member(db, org_id: str, user_id: str, role: str = "member") -> None:
    invalidate_memberships(user_id)
    with db.pool().connection() as con:
        con.execute("INSERT INTO public.memberships (org_id, user_id, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT (org_id, user_id) DO UPDATE SET role = EXCLUDED.role", (org_id, user_id, role))
        con.commit()


def remove_member(db, org_id: str, user_id: str) -> None:
    invalidate_memberships(user_id)
    with db.pool().connection() as con:
        con.execute("DELETE FROM public.memberships WHERE org_id = %s AND user_id = %s", (org_id, user_id))
        con.commit()


_member_cache: dict[str, tuple[float, "User"]] = {}
MEMBER_TTL = 60.0


def invalidate_memberships(user_id: str | None = None) -> None:
    if user_id:
        _member_cache.pop(user_id, None)
    else:
        _member_cache.clear()


def _free_credits() -> int:
    from bizzmind.plans import PLANS
    return PLANS["free"]["credits"]


def load_memberships(db, user_id: str, email: str) -> User:
    """User + org memberships (cached 60 s per process); first login creates a
    personal organisation or adopts the orphan one holding pre-Auth projects."""
    hit = _member_cache.get(user_id)
    if hit and hit[0] > time.time():
        return hit[1]
    u = _load_memberships(db, user_id, email)
    _member_cache[user_id] = (time.time() + MEMBER_TTL, u)
    return u


def _load_memberships(db, user_id: str, email: str) -> User:
    with db.pool().connection() as con:
        rows = con.execute("SELECT org_id, role FROM public.memberships WHERE user_id = %s", (user_id,)).fetchall()
        if not rows:
            # adopt an organisation that has projects but no members yet (pre-Auth data),
            # otherwise create a personal one
            orphan = con.execute(
                "SELECT o.id FROM public.organizations o WHERE NOT EXISTS "
                "(SELECT 1 FROM public.memberships m WHERE m.org_id = o.id) "
                "AND EXISTS (SELECT 1 FROM public.projects p WHERE p.org_id = o.id) ORDER BY o.created_at LIMIT 1"
            ).fetchone()
            org = orphan[0] if orphan else con.execute(
                "INSERT INTO public.organizations (name, credits_quota) VALUES (%s, %s) RETURNING id",
                (email.split("@")[-1] or email, _free_credits())).fetchone()[0]
            con.execute("INSERT INTO public.memberships (org_id, user_id, role) VALUES (%s, %s, 'owner')",
                        (org, user_id))
            con.commit()
            rows = [(org, "owner")]
            log.info(f"auth: first login for {email} — organisation created")
    return User(id=user_id, email=email,
                orgs=[str(r[0]) for r in rows], roles={str(r[0]): r[1] for r in rows})
