"""Gamma (gamma.app) presentation generation."""

import json
import re
import secrets
from datetime import datetime

import storage
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bizzmind.config import DATA_DIR, GAMMA_API_KEY, PUBLIC_BASE_URL, _short, log
from bizzmind.i18n import LANGS, T, req_lang
from bizzmind.project import get_project
from bizzmind.brand import brand_colors, brand_dir, brand_logo_path


# ------------------------------------------------------------------ Gamma
# Presentation generation through gamma.app's public API. The frontend asks
# for the available controls (themes, options), the user picks, we build the
# deck text (+ public image URLs when PUBLIC_BASE_URL is set) and poll.
GAMMA_API = "https://public-api.gamma.app/v1.0"
PUB_DIR = DATA_DIR / "pub"
PUB_DIR.mkdir(exist_ok=True)
_gamma_theme_cache: dict = {"at": 0.0, "data": None}


def _gamma_call(method: str, path: str, body: dict | None = None, lang: str = "bg") -> dict:
    import urllib.request
    import urllib.error
    if not GAMMA_API_KEY:
        raise HTTPException(503, T(lang, "err_gamma_not_configured"))
    req = urllib.request.Request(
        GAMMA_API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-API-KEY": GAMMA_API_KEY, "Content-Type": "application/json",
                 "Accept": "application/json",
                 # Cloudflare in front of Gamma rejects the default Python-urllib UA
                 "User-Agent": "Bizzmind/1.0 (+https://bizzmind.ai)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        log.info(f"gamma: {method} {path} -> {e.code} {detail}")
        raise HTTPException(502, T(lang, "err_gamma_status", code=e.code, detail=detail))
    except Exception as e:
        raise HTTPException(502, T(lang, "err_gamma_unreachable", detail=_short(e)))


def gamma_options(request: Request):
    """Everything the UI needs to render Gamma's generation controls."""
    import time
    L = req_lang(request)
    if not GAMMA_API_KEY:
        return {"enabled": False}
    if not _gamma_theme_cache["data"] or time.time() - _gamma_theme_cache["at"] > 3600:
        themes, cursor = [], None
        for _ in range(10):
            q = "?limit=50" + (f"&after={cursor}" if cursor else "")
            d = _gamma_call("GET", "/themes" + q, lang=L)
            themes += d.get("data", [])
            cursor = d.get("nextCursor")
            if not d.get("hasMore") or not cursor:
                break
        _gamma_theme_cache.update(at=time.time(), data=themes)
    return {
        "enabled": True,
        "public_images": bool(PUBLIC_BASE_URL) or storage.enabled(),
        "themes": _gamma_theme_cache["data"],
        "text_modes": [
            {"id": "preserve", "label": T(L, "g_preserve"), "hint": T(L, "g_preserve_hint")},
            {"id": "condense", "label": T(L, "g_condense"), "hint": T(L, "g_condense_hint")},
            {"id": "generate", "label": T(L, "g_generate"), "hint": T(L, "g_generate_hint")},
        ],
        "image_sources": [
            {"id": "noImages", "label": T(L, "g_img_none")},
            {"id": "themeAccent", "label": T(L, "g_img_theme")},
            {"id": "aiGenerated", "label": T(L, "g_img_ai")},
            {"id": "pictographic", "label": T(L, "g_img_picto")},
            {"id": "webFreeToUseCommercially", "label": T(L, "g_img_stock")},
        ],
        "dimensions": ["16x9", "4x3", "fluid"],
        "export_as": ["pdf", "pptx"],
        "languages": [{"id": "bg", "label": T(L, "lang_bg")}, {"id": "en", "label": T(L, "lang_en")}],
        "default_language": L,
    }


class GammaSlide(BaseModel):
    heading: str = ""                  # section heading (divider), optional
    title: str
    narrative: str = ""
    image: str | None = None           # dataURL PNG
    columns: list[str] | None = None
    rows: list[list] | None = None


class GammaRequest(BaseModel):
    title: str
    subtitle: str = ""
    slides: list[GammaSlide]
    takeaways: list[dict] = []
    theme_id: str | None = None
    text_mode: str = "preserve"
    num_cards: int | None = None
    image_source: str = "noImages"
    dimensions: str = "16x9"
    export_as: str = "pdf"
    language: str | None = None        # None -> follows the UI language
    tone: str = ""
    extra_instructions: str = ""


def _md_table(columns: list, rows: list, limit: int = 12) -> str:
    cols = [str(c).replace("_", " ") for c in columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows[:limit]:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(out)


def gamma_generate(pid: str, req: GammaRequest, request: Request):
    import base64
    import shutil
    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    req.language = req.language if req.language in LANGS else lang
    token = secrets.token_urlsafe(12)
    out_dir = PUB_DIR / token
    out_dir.mkdir()
    warnings = []

    def publish(name: str, data: bytes) -> str | None:
        (out_dir / name).write_bytes(data)
        if storage.enabled():
            try:
                storage.put(f"{pid}/pub/{token}/{name}", data)
                return storage.signed_url(f"{pid}/pub/{token}/{name}", 7 * 24 * 3600)
            except storage.StorageError as e:
                log.info(f"[{pid}] gamma: storage publish failed — {_short(e)}")
        return f"{PUBLIC_BASE_URL}/pub/{token}/{name}" if PUBLIC_BASE_URL else None

    # logo
    logo_url = None
    logo = brand_logo_path(proj)
    if logo:
        logo_url = publish("logo" + logo.suffix.lower(), logo.read_bytes())

    # deck text — one card per "---"
    cards = []
    cover = f"# {req.title}"
    if req.subtitle:
        cover += f"\n\n{req.subtitle}"
    cover += f"\n\n{proj.meta['name']} · {datetime.now().strftime('%d.%m.%Y')}"
    cards.append(cover)   # logo comes via headerFooter (small, every card incl. cover)
    last_heading = None
    dropped_images = 0
    for i, sl in enumerate(req.slides):
        if sl.heading and sl.heading != last_heading:
            cards.append(f"# {sl.heading}")
            last_heading = sl.heading
        body = f"## {sl.title}"
        if sl.narrative:
            body += f"\n\n{sl.narrative}"
        embedded = False
        if sl.image and sl.image.startswith("data:image"):
            raw = base64.b64decode(sl.image.split(",", 1)[1])
            url = publish(f"chart-{i + 1}.png", raw)
            if url:
                body += f"\n\n{url}"
                embedded = True
            else:
                dropped_images += 1
        # data table only when the chart itself could not be embedded (or it IS a table)
        if sl.columns and sl.rows and not embedded:
            body += "\n\n" + _md_table(sl.columns, sl.rows)
        cards.append(body)
    if req.takeaways:
        body = f"# {T(req.language, 'gamma_takeaways')}\n\n" + "\n".join(
            f"* **{t.get('title', '')}** — {t.get('text', '')}" for t in req.takeaways[:6])
        cards.append(body)
    input_text = "\n---\n".join(cards)
    if dropped_images:
        warnings.append(T(lang, "gamma_warn_images", n=dropped_images))

    # brand guidance — colours & fonts from the brand book
    colors = brand_colors(proj)
    fonts = []
    bj = brand_dir(proj) / "brand.json"
    if bj.exists():
        try:
            fonts = json.loads(bj.read_text()).get("fonts", [])
        except Exception:
            pass
    instr = []
    if colors:
        instr.append(f"Brand palette (hex): {', '.join(colors[:7])}. Primary = {colors[0]}; "
                     f"use it for headings and accents, neutrals for backgrounds.")
    if fonts:
        instr.append(f"Brand fonts, in order of preference: {', '.join(fonts[:3])}.")
    instr.append("This is a data-driven business report: keep each chart image large and "
                 "unmodified, one chart per card, headline left / chart right. "
                 "Do not invent numbers — use only the figures given.")
    if req.tone:
        instr.append(f"Tone: {req.tone}.")
    if req.extra_instructions:
        instr.append(req.extra_instructions)

    body = {
        "inputText": input_text,
        "title": req.title[:500],
        "textMode": req.text_mode,
        "format": "presentation",
        "exportAs": req.export_as,
        "cardSplit": "inputTextBreaks",
        "additionalInstructions": " ".join(instr)[:2000],
        "textOptions": ({"language": req.language} if req.text_mode == "preserve"
                        else {"language": req.language, "amount": "medium"}),
        "imageOptions": {"source": req.image_source},
        "cardOptions": {"dimensions": req.dimensions},
        "sharingOptions": {"workspaceAccess": "edit", "externalAccess": "view"},
    }
    if req.theme_id:
        body["themeId"] = req.theme_id
    if req.num_cards:
        body["numCards"] = max(1, min(75, req.num_cards))
    if req.image_source == "aiGenerated":
        body["imageOptions"]["style"] = "clean, minimal, corporate, brand colours"
    hf = {"bottomRight": {"type": "cardNumber"}}
    if logo_url:
        hf["topRight"] = {"type": "image", "source": "custom", "src": logo_url, "size": "md"}
    body["cardOptions"]["headerFooter"] = hf

    log.info(f"[{pid}] gamma: generating — {len(cards)} карти, тема={req.theme_id or 'default'}, "
             f"{req.text_mode}/{req.image_source}/{req.export_as}, картинки={'да' if PUBLIC_BASE_URL else 'не'}")
    try:
        d = _gamma_call("POST", "/generations", body, lang=lang)
    except HTTPException:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise
    if d.get("warnings"):
        warnings.append(str(d["warnings"]))
    return {"generation_id": d.get("generationId"), "warnings": warnings}


def gamma_status(gid: str):
    d = _gamma_call("GET", f"/generations/{gid}")
    if d.get("status") in ("completed", "failed"):
        log.info(f"gamma: {gid} -> {d.get('status')} {d.get('gammaUrl', '')}")
    return {"status": d.get("status"), "gamma_url": d.get("gammaUrl"),
            "export_url": d.get("exportUrl"), "credits": d.get("credits"),
            "error": d.get("error")}


def pub_file(token: str, name: str):
    """Unauthenticated assets for Gamma's fetchers (unguessable token path)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", token) or "/" in name or name.startswith("."):
        raise HTTPException(404)
    f = PUB_DIR / token / name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)
