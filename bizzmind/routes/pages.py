"""HTML pages, /login redirect logic and the public asset path used by Gamma."""

import auth as sb_auth
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from bizzmind.config import NO_CACHE, ROOT
from bizzmind import gamma

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    access = request.cookies.get(sb_auth.ACCESS_COOKIE)
    try:
        if access and sb_auth.get_user(access):
            return RedirectResponse("/app")
    except sb_auth.AuthError:
        pass
    return FileResponse(ROOT / "static" / "login.html", headers=NO_CACHE)


@router.get("/")
def landing():
    return FileResponse(ROOT / "static" / "landing.html", headers=NO_CACHE)


@router.get("/app")
def app_page():
    return FileResponse(ROOT / "static" / "app.html", headers=NO_CACHE)


@router.get("/pub/{token}/{name}")
def pub_file(token: str, name: str):
    """Unauthenticated assets for Gamma's fetchers (unguessable token path)."""
    return gamma.pub_file(token, name)
