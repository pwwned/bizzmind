"""Inceptiq Analytics — prototype backend.

Multi-project: every project is an isolated environment (own PostgreSQL schema,
chat transcript, knowledge notes, filters, dashboard, uploaded files,
PROGRESS.md) living under data/projects/<id>/.

Pipeline per project: Excel/CSV upload -> PostgreSQL (Supabase) -> natural-language chat ->
Claude interviews the user + generates SQL/filters/chart specs via tool use ->
frontend renders a live, filterable dashboard.
"""

import asyncio
import decimal
import hashlib
import json
import logging
import os
import re
import secrets
from datetime import datetime
import shutil
import time
import uuid
from pathlib import Path

import anthropic
import db
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# "subscription": local testing via Claude Agent SDK (uses your Claude Code
# login / subscription). "api": production path via the Anthropic API.
def _load_dotenv(path: Path) -> None:
    """Tiny .env reader (KEY=VALUE, # comments) — no extra dependency."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_dotenv(Path(__file__).parent / ".env")

AI_BACKEND = os.environ.get("AI_BACKEND", "subscription")
GAMMA_API_KEY = os.environ.get("GAMMA_API_KEY", "")
# Public https origin of this server — Gamma's servers fetch chart images and
# the logo from here. Without it the deck is generated text-only.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

logging.basicConfig(level=logging.INFO, format="%(asctime)s STEP | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("studio")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

MODEL = "claude-opus-5"
MAX_CHART_ROWS = 500
MAX_PREVIEW_ROWS = 50
MAX_SERIES = 8
SUB_TIMEOUT_S = 600

app = FastAPI(title="Inceptiq Analytics (prototype)")
client = anthropic.Anthropic()

# ------------------------------------------------------------------- auth

USERS_PATH = DATA_DIR / "users.json"
SESSIONS_PATH = DATA_DIR / "sessions.json"
USERS: dict = json.loads(USERS_PATH.read_text()) if USERS_PATH.exists() else {}
SESSIONS: dict = json.loads(SESSIONS_PATH.read_text()) if SESSIONS_PATH.exists() else {}


def hash_password(password: str, salt: str | None = None) -> tuple:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt), 200_000).hex()
    return salt, digest


def verify_password(password: str, salt: str, digest: str) -> bool:
    return secrets.compare_digest(hash_password(password, salt)[1], digest)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    p = request.url.path
    if (p in ("/", "/login") or p.startswith("/static/") or p.startswith("/pub/")
            or p.startswith("/api/auth/")):
        return await call_next(request)
    token = request.cookies.get("session")
    if token and token in SESSIONS:
        return await call_next(request)
    if p.startswith("/api/"):
        return JSONResponse({"detail": T(req_lang(request), "not_logged_in")}, status_code=401)
    return RedirectResponse("/login")


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def auth_login(req: LoginRequest, request: Request):
    user = USERS.get(req.email.strip().lower())
    if not user or not verify_password(req.password, user["salt"], user["hash"]):
        log.info(f"auth: failed login for '{req.email}'")
        return JSONResponse({"detail": T(req_lang(request), "bad_credentials")}, status_code=401)
    token = secrets.token_hex(32)
    SESSIONS[token] = {"email": req.email.strip().lower(),
                       "created": time.strftime("%Y-%m-%d %H:%M")}
    SESSIONS_PATH.write_text(json.dumps(SESSIONS))
    log.info(f"auth: '{req.email}' logged in")
    resp = JSONResponse({"ok": True, "email": req.email.strip().lower()})
    resp.set_cookie("session", token, httponly=True, samesite="lax",
                    max_age=60 * 60 * 24 * 30)
    return resp


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.cookies.get("session")
    if token:
        SESSIONS.pop(token, None)
        SESSIONS_PATH.write_text(json.dumps(SESSIONS))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    log.info("auth: logged out")
    return resp


@app.get("/api/auth/me")
def auth_me(request: Request):
    token = request.cookies.get("session")
    sess = SESSIONS.get(token) if token else None
    if not sess:
        return JSONResponse({"detail": "not logged in"}, status_code=401)
    return {"email": sess["email"]}


@app.get("/login")
def login_page(request: Request):
    token = request.cookies.get("session")
    if token and token in SESSIONS:
        return RedirectResponse("/app")
    return FileResponse(ROOT / "static" / "login.html", headers=NO_CACHE)


# ---------------------------------------------------------------- i18n
# The UI language travels in the `lang` cookie (set by static/i18n/core.js).
# Server-side texts (errors, activity feed, PDF labels) go through T();
# AI prompts get the language name so every generated label matches the UI.
LANGS = ("bg", "en")
LANG_NAMES = {"bg": "Bulgarian", "en": "English"}
MSG: dict = {
    "bg": {
        "act_translating": "🌐 Превеждам съдържанието на дашборда ({n} текста)…",
        "act_translated": "🌐 Преведох {n} текста",
        # auth / projects
        "not_logged_in": "Не си влязъл — влез отново.",
        "bad_credentials": "Грешен имейл или парола.",
        "new_project": "Нов проект",
        # activity feed (agent tool callbacks)
        "act_verify": "🧪 Проверка на дашборда: {status}",
        "act_verify_ok": "✅ всичко работи",
        "act_verify_err": "⚠️ има грешки — поправям",
        "act_sql_retry": "🔁 Коригирам заявката (пробвам друг подход)…",
        "act_tool_error": "⚠️ {name}: {detail}",
        "act_sql_look": "🔍 Разглеждам: {sql}",
        "act_note": "💾 Запомних: {note}",
        "act_filter": "🎛 Филтър „{label}“",
        "act_view": "🧩 Изглед „{name}“ — {desc}",
        "act_view_drop": "🧩 Премахнах изглед „{name}“",
        "act_chart": "📊 Графика „{title}“",
        "act_chart_upd": "✏️ Обнових графика „{title}“",
        "act_chart_del": "🗑 Премахнах графика #{id}",
        "act_questions": "❓ Подготвям {n} въпроса с предложения",
        "act_new_session": "🔌 Нова AI сесия",
        "act_session_recap": " — продължавам разговора от резюме",
        "act_thinking": "🧠 Мисля — чета контекста и планирам стъпките…",
        "act_table_loaded": "📥 Таблица „{table}“ — {rows} реда, {cols} колони",
        "act_edit": "✏️ Редакция: {table}.{column} → {value}",
        "act_brand_extracted": "🎨 Извлякох {colors} цвята и {fonts} шрифта от книгата",
        "act_brand_file": "🎨 Бранд файл „{name}“",
        "act_deck_writing": "📽 Пиша съдържанието на презентацията…",
        "act_pdf": "📄 PDF отчет ({n} графики)",
        # chat transcript events
        "chat_files_loaded": "Качени файлове → таблици: {tables}",
        "chat_context": "Какво знам за данните: {text}",
        "chat_goal": "Какво искам да постигна: {text}",
        "chat_deck_ready": "Подготвих съдържанието и брифа на презентацията.",
        # errors (HTTP details)
        "err_no_table": "Няма таблица '{table}'.",
        "err_no_column": "Няма колона '{column}'.",
        "err_not_number": "'{value}' не е число, а колоната е числова.",
        "err_brand_ext": "'{name}': за бранд приемам PDF, PNG, JPG или SVG.",
        "err_brand_missing": "Няма такъв бранд файл.",
        "err_deck_no_charts": "Няма графики, от които да направя презентация.",
        "err_deck_invalid": "AI не върна валидна презентация — опитай пак.",
        "err_deck_json": "AI върна невалиден JSON за презентацията — опитай пак.",
        "err_ai_timeout": "AI отговаря прекалено дълго и заявката беше прекъсната. "
                          "Опитай пак — при много файлове първият преглед може да е бавен.",
        "err_ai_failed": "AI заявката се провали: {detail}",
        "err_ai_unreachable": "Няма връзка с AI услугата. Провери мрежата.",
        "err_ai_sub_failed": "AI заявката (абонамент) се провали: {detail}",
        "err_ai_refusal": "Съжалявам — не мога да помогна с това. Попитай нещо за данните си.",
        "err_gamma_not_configured": "Gamma не е настроена — липсва GAMMA_API_KEY в .env",
        "err_gamma_status": "Gamma отговори {code}: {detail}",
        "err_gamma_unreachable": "Gamma недостъпна — {detail}",
        # deck / PDF / Gamma content
        "deck_no_brand": "няма качен бранд бук",
        "pdf_report": "Аналитичен отчет",
        "pdf_page": "стр. {n}",
        "pdf_filters": "Филтри: {text}",
        "date_fmt": "%d.%m.%Y",
        "gamma_takeaways": "Изводи и препоръки",
        "gamma_warn_images": "{n} графики не са вградени — сървърът няма публичен адрес "
                             "(PUBLIC_BASE_URL). Gamma получава данните им като таблици.",
        "g_preserve": "Запази текста", "g_preserve_hint": "Точно нашите заглавия и изводи",
        "g_condense": "Сбито", "g_condense_hint": "Gamma съкращава до същественото",
        "g_generate": "Разгърни", "g_generate_hint": "Gamma дописва и разширява",
        "g_img_none": "Само нашите графики", "g_img_theme": "Акценти от темата",
        "g_img_ai": "AI илюстрации", "g_img_picto": "Пиктограми", "g_img_stock": "Стокови снимки",
        "lang_bg": "Български", "lang_en": "English",
    },
    "en": {
        "act_translating": "🌐 Translating the dashboard content ({n} texts)…",
        "act_translated": "🌐 Translated {n} texts",
        # auth / projects
        "not_logged_in": "You are not signed in — please sign in again.",
        "bad_credentials": "Incorrect email or password.",
        "new_project": "New project",
        # activity feed (agent tool callbacks)
        "act_verify": "🧪 Dashboard check: {status}",
        "act_verify_ok": "✅ everything works",
        "act_verify_err": "⚠️ found issues — fixing them",
        "act_sql_retry": "🔁 Adjusting the query (trying another approach)…",
        "act_tool_error": "⚠️ {name}: {detail}",
        "act_sql_look": "🔍 Looking at: {sql}",
        "act_note": "💾 Noted: {note}",
        "act_filter": "🎛 Filter “{label}”",
        "act_view": "🧩 View “{name}” — {desc}",
        "act_view_drop": "🧩 Removed view “{name}”",
        "act_chart": "📊 Chart “{title}”",
        "act_chart_upd": "✏️ Updated chart “{title}”",
        "act_chart_del": "🗑 Removed chart #{id}",
        "act_questions": "❓ Preparing {n} questions with suggestions",
        "act_new_session": "🔌 New AI session",
        "act_session_recap": " — continuing the conversation from a summary",
        "act_thinking": "🧠 Thinking — reading the context and planning the steps…",
        "act_table_loaded": "📥 Table “{table}” — {rows} rows, {cols} columns",
        "act_edit": "✏️ Edit: {table}.{column} → {value}",
        "act_brand_extracted": "🎨 Extracted {colors} colours and {fonts} fonts from the brand book",
        "act_brand_file": "🎨 Brand file “{name}”",
        "act_deck_writing": "📽 Writing the presentation content…",
        "act_pdf": "📄 PDF report ({n} charts)",
        # chat transcript events
        "chat_files_loaded": "Uploaded files → tables: {tables}",
        "chat_context": "What I know about the data: {text}",
        "chat_goal": "What I want to achieve: {text}",
        "chat_deck_ready": "The presentation content and design brief are ready.",
        # errors (HTTP details)
        "err_no_table": "There is no table '{table}'.",
        "err_no_column": "There is no column '{column}'.",
        "err_not_number": "'{value}' is not a number, but the column is numeric.",
        "err_brand_ext": "'{name}': brand files must be PDF, PNG, JPG or SVG.",
        "err_brand_missing": "No such brand file.",
        "err_deck_no_charts": "There are no charts to build a presentation from.",
        "err_deck_invalid": "The AI did not return a valid presentation — please try again.",
        "err_deck_json": "The AI returned invalid JSON for the presentation — please try again.",
        "err_ai_timeout": "The AI took too long and the request was cancelled. "
                          "Try again — with many files the first review can be slow.",
        "err_ai_failed": "AI request failed: {detail}",
        "err_ai_unreachable": "Could not reach the AI service. Check your network.",
        "err_ai_sub_failed": "Subscription AI request failed: {detail}",
        "err_ai_refusal": "Sorry — I can't help with that request. Try asking about your data.",
        "err_gamma_not_configured": "Gamma is not configured — GAMMA_API_KEY is missing in .env",
        "err_gamma_status": "Gamma responded {code}: {detail}",
        "err_gamma_unreachable": "Gamma is unreachable — {detail}",
        # deck / PDF / Gamma content
        "deck_no_brand": "no brand book uploaded",
        "pdf_report": "Analytics report",
        "pdf_page": "p. {n}",
        "pdf_filters": "Filters: {text}",
        "date_fmt": "%d %b %Y",
        "gamma_takeaways": "Key takeaways and recommendations",
        "gamma_warn_images": "{n} charts were not embedded — the server has no public address "
                             "(PUBLIC_BASE_URL). Gamma receives their data as tables instead.",
        "g_preserve": "Keep the text", "g_preserve_hint": "Exactly our headlines and takeaways",
        "g_condense": "Condense", "g_condense_hint": "Gamma trims to the essentials",
        "g_generate": "Expand", "g_generate_hint": "Gamma elaborates and extends",
        "g_img_none": "Only our charts", "g_img_theme": "Theme accents",
        "g_img_ai": "AI illustrations", "g_img_picto": "Pictograms", "g_img_stock": "Stock photos",
        "lang_bg": "Български", "lang_en": "English",
    },
}


def req_lang(request: Request | None) -> str:
    try:
        l = request.cookies.get("lang", "") if request is not None else ""
    except Exception:
        l = ""
    return l if l in LANGS else "bg"


def T(lang: str, key: str, **kw) -> str:
    s = MSG.get(lang, {}).get(key)
    if s is None:
        s = MSG["bg"].get(key, key)
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError):
        return s


def _short(s, n=140):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------- projects

class Project:
    """One isolated analytics environment."""

    def __init__(self, pid: str):
        self.id = pid
        self.dir = PROJECTS_DIR / pid
        self.dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir = self.dir / "uploads"
        self.uploads_dir.mkdir(exist_ok=True)
        self.db_path = self.dir / "project.duckdb"   # legacy DuckDB file (migration only)
        self._meta_p = self.dir / "meta.json"
        self._chat_p = self.dir / "chat.json"
        self._notes_p = self.dir / "notes.json"
        self._filters_p = self.dir / "filters.json"
        self._dash_p = self.dir / "dashboard.json"
        self.progress_p = self.dir / "PROGRESS.md"

        def _load(p, default):
            try:
                return json.loads(p.read_text()) if p.exists() else default
            except Exception:
                return default

        self.meta = _load(self._meta_p, {"name": pid, "created": time.strftime("%Y-%m-%d"),
                                         "files": {}})
        self.meta.setdefault("files", {})
        self.chat = _load(self._chat_p, [])
        self.notes = _load(self._notes_p, [])
        self.filters = _load(self._filters_p, [])
        self.dashboard = _load(self._dash_p, [])
        self.chart_seq = max((c["id"] for c in self.dashboard), default=0)

        self.messages: list = []          # API-backend conversation (in-memory)
        self.sub_client = None            # Agent SDK session
        self.new_charts: list = []        # charts created during current turn
        self.new_questions: list = []     # interview questions from current turn
        self.activity: list = []
        self.act_seq = 0
        self.lang = "bg"                  # UI language of the request driving this turn
        self.sub_lang: str | None = None  # language the SDK session's prompt was built for

    # ---- persistence
    def save_meta(self):    self._meta_p.write_text(json.dumps(self.meta, ensure_ascii=False))
    def save_chat(self):    self._chat_p.write_text(json.dumps(self.chat, ensure_ascii=False))
    def save_notes(self):   self._notes_p.write_text(json.dumps(self.notes, ensure_ascii=False))
    def save_filters(self): self._filters_p.write_text(json.dumps(self.filters, ensure_ascii=False))
    def save_dash(self):    self._dash_p.write_text(json.dumps(self.dashboard, ensure_ascii=False))

    def add_chat(self, role: str, text: str, questions: list | None = None):
        if not text and not questions:
            return
        entry = {"role": role, "text": text, "ts": time.strftime("%Y-%m-%d %H:%M")}
        if questions:
            entry["questions"] = questions
        self.chat.append(entry)
        self.save_chat()

    def log_activity(self, kind: str, text: str):
        self.act_seq += 1
        self.activity.append({"seq": self.act_seq, "kind": kind, "text": text,
                              "ts": time.strftime("%H:%M:%S")})
        del self.activity[:-200]


PROJECTS: dict = {}


def backfill_file_map(proj: Project):
    """Uploads made before per-file tracking existed: rebuild filename->tables
    from the stored originals (runs once, then persists)."""
    if proj.meta["files"]:
        return
    uploads = [f for f in sorted(proj.uploads_dir.iterdir())
               if f.suffix.lower() in (".xlsx", ".xls", ".csv")] if proj.uploads_dir.exists() else []
    if not uploads:
        return
    for f in uploads:
        try:
            frames = load_frames_from_upload(f.name, f.read_bytes())
            proj.meta["files"][f.name] = list(frames.keys())
        except Exception as e:
            log.info(f"[{proj.id}] backfill: could not parse '{f.name}' — {_short(e)}")
    proj.save_meta()
    log.info(f"[{proj.id}] backfill: file map rebuilt for {len(proj.meta['files'])} file(s)")


def get_project(pid: str) -> Project:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", pid) or not (PROJECTS_DIR / pid).exists():
        raise HTTPException(404, f"Unknown project '{pid}'")
    if pid not in PROJECTS:
        PROJECTS[pid] = Project(pid)
        backfill_file_map(PROJECTS[pid])
        try:
            extract_brand_assets(PROJECTS[pid])   # backfill for older uploads
        except Exception as e:
            log.info(f"[{pid}] brand backfill failed — {_short(e)}")
    return PROJECTS[pid]


def migrate_legacy_project():
    """Move the old single-project layout into data/projects/sidaya-pharma."""
    legacy_db = DATA_DIR / "project.duckdb"
    if not legacy_db.exists():
        return
    pid = "sidaya-pharma"
    pdir = PROJECTS_DIR / pid
    if pdir.exists():
        return
    pdir.mkdir(parents=True)
    for src, dst in [(legacy_db, "project.duckdb"), (DATA_DIR / "chat.json", "chat.json"),
                     (DATA_DIR / "notes.json", "notes.json"),
                     (DATA_DIR / "filters.json", "filters.json"),
                     (DATA_DIR / "dashboard.json", "dashboard.json"),
                     (DATA_DIR / "PROGRESS.md", "PROGRESS.md")]:
        if src.exists():
            shutil.move(str(src), str(pdir / dst))
    if (DATA_DIR / "uploads").exists():
        shutil.move(str(DATA_DIR / "uploads"), str(pdir / "uploads"))
    (pdir / "meta.json").write_text(json.dumps(
        {"name": "Sidaya Pharma", "created": time.strftime("%Y-%m-%d"), "files": {}},
        ensure_ascii=False))
    log.info(f"migrated legacy single-project data into projects/{pid}")


migrate_legacy_project()


def conversation_recap(proj: Project, limit: int = 14) -> str:
    if not proj.chat:
        return ""
    who = {"user": "User", "ai": "You (assistant)", "event": "Event"}
    lines = [f"{who.get(m['role'], m['role'])}: {_short(m['text'], 400)}" for m in proj.chat[-limit:]]
    return ("<conversation_recap>\nThe app restarted. This is the recent conversation — "
            "continue from here; do NOT restart the interview or re-ask answered questions:\n"
            + "\n".join(lines) + "\n</conversation_recap>\n\n")


def write_progress(proj: Project):
    try:
        parts = [f"# {proj.meta['name']} — progress",
                 f"_Updated: {time.strftime('%Y-%m-%d %H:%M')}_", "",
                 "## Data (tables)"]
        parts += [f"- **{t['table']}** — {t['rows']} rows: "
                  f"{', '.join(c['name'] for c in t['columns'])}"
                  for t in describe_schema(proj)] or ["- (none)"]
        parts += ["", "## Knowledge (what the AI knows)"] + (
            [f"- {n}" for n in proj.notes] or ["- (nothing yet)"])
        parts += ["", "## Filters"] + (
            [f"- `{f['id']}` — {f['label']} ({f['type']})" for f in proj.filters] or ["- (none)"])
        parts += ["", "## Dashboard charts"] + (
            [f"- #{c['id']} **{c['title']}** ({c['chart_type']}) — {c['insight']}"
             for c in proj.dashboard] or ["- (none)"])
        proj.progress_p.write_text("\n".join(parts))
    except Exception as e:
        log.info(f"progress: could not write PROGRESS.md — {_short(e)}")


# ---------------------------------------------------------------- ingestion

def sanitize_identifier(name: str) -> str:
    # \w keeps Unicode letters — Bulgarian/Cyrillic headers must survive
    name = re.sub(r"[^\w]+", "_", str(name).strip()).strip("_").lower()
    if not name:
        name = "col"
    if name[0].isdigit():
        name = "_" + name
    return name


def detect_header_row(df_raw: pd.DataFrame, max_scan: int = 15) -> int:
    """Real-world exports often have title/logo rows above the actual header.
    Score the first rows and pick the one that looks most like a header."""
    best, best_score = 0, float("-inf")
    for i in range(min(max_scan, len(df_raw))):
        row = df_raw.iloc[i]
        vals = [v for v in row if pd.notna(v) and str(v).strip() != ""]
        if not vals:
            continue
        n_text = sum(isinstance(v, str) for v in vals)
        n_unique = len({str(v).strip().lower() for v in vals})
        n_empty = len(row) - len(vals)
        # headers hold labels and whole numbers (months/years), never decimals;
        # prefer earlier rows so data rows can't outscore the real header
        n_decimal = sum(1 for v in vals
                        if isinstance(v, float) and not float(v).is_integer())
        score = n_text * 2 + n_unique - n_empty - 3 * n_decimal - 0.5 * i
        if score > best_score:
            best, best_score = i, score
    return best


def frame_from_raw(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Find the header row, promote it (merging two-row headers), re-infer
    numeric columns."""
    df_raw = df_raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if df_raw.empty:
        return df_raw
    hdr = detect_header_row(df_raw)
    if hdr > 0:
        log.info(f"ingest: header found on row {hdr + 1}, skipped {hdr} title row(s)")

    def cell_text(v):
        if pd.isna(v):
            return ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v).strip()

    # Two-row headers (pivot exports): a year/label row above the header row
    # spans month-number columns via merged cells -> "2024" + "10" = "2024_10".
    hdr_vals = df_raw.iloc[hdr]
    above = df_raw.iloc[hdr - 1].ffill() if hdr > 0 else None
    names = []
    for i in range(df_raw.shape[1]):
        h = cell_text(hdr_vals.iloc[i])
        a = cell_text(above.iloc[i]) if above is not None else ""
        has_letters = bool(re.search(r"[^\W\d_]", h))
        if h and has_letters:
            names.append(h)
        elif h and a:
            names.append(f"{a}_{h}")
        elif h:
            names.append(h)
        elif a:
            names.append(a)
        else:
            names.append(f"col_{i + 1}")

    df = df_raw.iloc[hdr + 1:].reset_index(drop=True)
    df.columns = names
    df = df.dropna(how="all").dropna(axis=1, how="all")
    # positional access: duplicate header names make df[name] return a DataFrame
    for i in range(df.shape[1]):
        s = df.iloc[:, i]
        if s.dtype == object:
            num = pd.to_numeric(s, errors="coerce")
            non_null = s.notna().sum()
            if non_null and num.notna().sum() >= 0.9 * non_null:
                df.isetitem(i, num)
    return df


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(how="all").dropna(axis=1, how="all")
    seen: dict = {}
    cols = []
    for c in df.columns:
        base = sanitize_identifier(c)
        seen[base] = seen.get(base, 0) + 1
        cols.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    df.columns = cols
    return df


def load_frames_from_upload(filename: str, payload: bytes) -> dict:
    """Return {table_name: DataFrame} for one uploaded file."""
    import io

    stem = sanitize_identifier(re.sub(r"^[^a-zA-Zа-яА-Я]+", "", Path(filename).stem) or Path(filename).stem)
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return {stem: clean_frame(frame_from_raw(pd.read_csv(io.BytesIO(payload), header=None)))}
    if suffix in (".xlsx", ".xls"):
        sheets = pd.read_excel(io.BytesIO(payload), sheet_name=None, header=None)
        frames = {}
        for sheet_name, df_raw in sheets.items():
            df = clean_frame(frame_from_raw(df_raw))
            if df.empty:
                continue
            name = stem if len(sheets) == 1 else f"{stem}_{sanitize_identifier(sheet_name)}"
            frames[name] = df
        return frames
    raise HTTPException(400, f"Unsupported file type: {suffix}. Upload .xlsx, .xls or .csv.")


def describe_schema(proj: Project) -> list:
    """Compact schema summary sent to the model: tables and semantic views,
    with columns and samples. Views carry their stored business description."""
    try:
        tables = db.list_tables(proj.id)
    except Exception as e:
        log.info(f"[{proj.id}] schema: {_short(e)}")
        return []
    view_meta = proj.meta.get("views", {})
    summary = []
    for t, kind in tables:
        try:
            cols = db.columns(proj.id, t)
            n_rows = db.row_count(proj.id, t)
            sample = db.query_df(proj.id, f'SELECT * FROM "{t}" LIMIT 2')
        except Exception as e:
            summary.append({"table": t, "kind": kind, "rows": 0, "columns": [],
                            "sample_rows": [], "error": _short(e, 90)})
            continue
        entry = {
            "table": t, "kind": kind,
            "rows": n_rows,
            "columns": [{"name": c[0], "type": c[1]} for c in cols],
            "sample_rows": frame_to_records(sample),
        }
        if kind == "view" and t in view_meta:
            entry["description"] = view_meta[t]
        summary.append(entry)
    return summary


# ------------------------------------------------------------ SQL execution

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|"
    r"install|load|export|import|call|set|reset|grant|revoke|truncate|vacuum|"
    r"refresh|comment|security|do)\b",
    re.IGNORECASE,
)


def _strip_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def pg_compat(sql: str) -> str:
    """Mechanical DuckDB -> PostgreSQL rewrites so legacy dashboards keep
    running: type names, TRY_CAST, integer division helpers."""
    out, i, parts = sql, 0, []
    # protect string literals from rewriting
    for m in re.finditer(r"'(?:[^']|'')*'", sql):
        parts.append(sql[i:m.start()]); parts.append(None); parts.append(m.group(0)); i = m.end()
    parts.append(sql[i:])
    res = []
    for p in parts:
        if p is None:
            continue
        if p.startswith("'"):
            res.append(p); continue
        p = re.sub(r"(\bAS\s+|::\s*)DOUBLE\b(?!\s+PRECISION)", r"\1DOUBLE PRECISION", p, flags=re.I)
        p = re.sub(r"::\s*DOUBLE PRECISION", "::double precision", p, flags=re.I)
        p = re.sub(r"\bAS\s+DOUBLE PRECISION", "AS DOUBLE PRECISION", p, flags=re.I)
        p = re.sub(r"\bAS\s+VARCHAR\b", "AS TEXT", p, flags=re.I)
        p = re.sub(r"::\s*VARCHAR\b", "::text", p, flags=re.I)
        p = re.sub(r"\bAS\s+(U?INTEGER|INT|INT64|HUGEINT)\b", "AS BIGINT", p, flags=re.I)
        p = re.sub(r"\bstrftime\(", "to_char(", p, flags=re.I)
        p = re.sub(r"\bepoch_ms\(", "epoch_ms_compat(", p, flags=re.I)
        res.append(p)
    out = "".join(res)
    # TRY_CAST(expr AS type) -> CASE WHEN expr::text ~ number THEN expr::type END (numeric types)
    def try_cast(m):
        inner = m.group(1)
        depth, j = 0, 0
        while j < len(inner):
            ch = inner[j]
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            elif depth == 0 and inner[j:j + 4].upper() == " AS ":
                expr, typ = inner[:j].strip(), inner[j + 4:].strip()
                if re.search(r"double|numeric|decimal|int|float|real", typ, re.I):
                    return (f"(CASE WHEN ({expr})::text ~ '^\\s*-?[0-9]+([.,][0-9]+)?\\s*$' "
                            f"THEN replace(({expr})::text, ',', '.')::{typ} END)")
                return f"(CASE WHEN ({expr}) IS NOT NULL THEN ({expr})::{typ} END)"
            j += 1
        return m.group(0)
    prev = None
    while prev != out:
        prev = out
        out = re.sub(r"\bTRY_CAST\s*\(((?:[^()]|\((?:[^()]|\([^()]*\))*\))*)\)", try_cast, out, count=1, flags=re.I)
    # DuckDB mode(x) -> ordered-set form (skip when already WITHIN GROUP)
    out = re.sub(r"\bmode\s*\(((?:[^()]|\((?:[^()]|\([^()]*\))*\))+)\)(?!\s*WITHIN)",
                 lambda m: f"mode() WITHIN GROUP (ORDER BY {m.group(1)})", out, flags=re.I)
    return out


def run_readonly_sql(proj: Project, sql: str, limit: int) -> pd.DataFrame:
    if FORBIDDEN_SQL.search(_strip_literals(sql)):
        raise ValueError("Only read-only SELECT queries are allowed.")
    body = sql.strip().rstrip(";")
    if ";" in _strip_literals(body):
        raise ValueError("One statement at a time.")
    try:
        return db.query_df(proj.id, pg_compat(body), limit=limit)
    except Exception as e:
        # surface Postgres' message only (no driver noise), first line
        raise ValueError(str(e).splitlines()[0]) from None


def frame_to_records(df: pd.DataFrame) -> list:
    if df.empty:
        return []
    # Decimal/UUID/etc. from Postgres -> JSON-safe
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: float(v) if isinstance(v, decimal.Decimal) else v)
    return json.loads(df.to_json(orient="records", date_format="iso"))


# ------------------------------------------------------------ dynamic filters

def resolve_filter_options(proj: Project, f: dict) -> list:
    if f.get("options"):
        return [str(o) for o in f["options"]]
    if f.get("options_sql"):
        try:
            df = run_readonly_sql(proj, f["options_sql"], 300)
            return [str(v) for v in df.iloc[:, 0].dropna().tolist()]
        except Exception:
            return []
    return []


def apply_filters_to_sql(proj: Project, sql: str, selections: dict) -> str:
    """Expand {{filter_id}} tokens. Multi filters become an IN(...) condition
    (or TRUE when nothing is selected); single filters are replaced by the
    selected option, validated against the filter's option list."""
    def repl(m):
        fid = m.group(1)
        f = next((x for x in proj.filters if x["id"] == fid), None)
        if f is None:
            return "TRUE"
        sel = selections.get(fid)
        if f["type"] == "single":
            opts = resolve_filter_options(proj, f)
            if isinstance(sel, str) and sel in opts:
                return sel
            return opts[0] if opts else "NULL"
        if not sel:
            return "TRUE"
        vals = ", ".join("'" + str(v).replace("'", "''") + "'" for v in sel)
        return f'(CAST("{f["column"]}" AS VARCHAR) IN ({vals}))'
    return re.sub(r"\{\{(\w+)\}\}", repl, sql)


def filters_with_options(proj: Project) -> list:
    return [{**f, "resolved_options": resolve_filter_options(proj, f)} for f in proj.filters]


# ------------------------------------------------------------ verification

def verify_dashboard(proj: Project) -> dict:
    """Mechanical health-check of the whole dashboard: every chart must run
    under real filter selections, declared fields must exist, filters must be
    unique, referenced and used. The AI runs this before declaring success."""
    errors, warnings = [], []
    fids = {f["id"] for f in proj.filters}

    seen_labels: dict = {}
    for f in proj.filters:
        key = f["label"].strip().lower()
        if key in seen_labels:
            errors.append(f"Duplicate filters for dimension '{f['label']}': "
                          f"'{seen_labels[key]}' and '{f['id']}' — merge them.")
        else:
            seen_labels[key] = f["id"]

    # selections to test with: none / everything active / alternate toggles
    sels = [{}]
    stress: dict = {}
    for f in proj.filters:
        opts = resolve_filter_options(proj, f)
        if not opts:
            errors.append(f"Filter '{f['id']}' ({f['label']}) has no options at all.")
            continue
        stress[f["id"]] = [opts[0]] if f["type"] == "multi" else opts[0]
    if stress:
        sels.append(stress)
    alt = {f["id"]: resolve_filter_options(proj, f)[1] for f in proj.filters
           if f["type"] == "single" and len(resolve_filter_options(proj, f)) > 1}
    if alt:
        sels.append(alt)

    # broken semantic views are dashboard-breaking by definition
    for entry in describe_schema(proj):
        if entry.get("error"):
            errors.append(f"View/table '{entry['table']}' is broken: "
                          f"{entry['error']} — fix it with define_view.")

    used: set = set()
    for c in proj.dashboard:
        toks = set(re.findall(r"\{\{(\w+)\}\}", c["sql"]))
        used |= toks
        dead = sorted(toks - fids)
        if dead:
            errors.append(f"Chart #{c['id']} '{c['title']}' references non-existent "
                          f"filters {dead} — rewire it with update_chart.")
            continue
        for sel in sels:
            try:
                df = run_readonly_sql(proj, apply_filters_to_sql(proj, c["sql"], sel),
                                      MAX_CHART_ROWS)
            except Exception as e:
                errors.append(f"Chart #{c['id']} '{c['title']}' fails with "
                              f"{'active' if sel else 'empty'} filters: {_short(e, 90)}")
                break
            missing = [x for x in [c["x_field"], *c["y_fields"]] if x not in df.columns]
            if missing:
                errors.append(f"Chart #{c['id']} '{c['title']}': declared fields "
                              f"{missing} are missing from the SQL result ({list(df.columns)[:6]}…).")
                break
        else:
            if not toks and proj.filters:
                warnings.append(f"Chart #{c['id']} '{c['title']}' is not wired to any filter.")

    for f in proj.filters:
        if f["id"] not in used:
            warnings.append(f"Filter '{f['id']}' ({f['label']}) is not used by any chart.")
    if proj.dashboard and proj.dashboard[0]["chart_type"] != "table":
        warnings.append("The first card is not the summary table — the standard wants it on top.")

    return {"ok": not errors, "charts": len(proj.dashboard),
            "filters": len(proj.filters), "errors": errors, "warnings": warnings}


# ------------------------------------------------------------------- tools

TOOLS = [
    {
        "name": "run_sql_query",
        "description": (
            "Run a read-only PostgreSQL query against the user's uploaded data to "
            "explore it or verify results. Returns up to 50 rows. Use double quotes "
            "around identifiers."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_data_context",
        "description": (
            "Permanently save a fact about the user's data so it is remembered in "
            "every future conversation: what a file/table represents, what a code or "
            "SKU means, units, currency, fiscal calendar, business definitions. Save "
            "each distinct fact as one short note, in the user's own terms. Use this "
            "immediately whenever the user explains something about their data."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
            "additionalProperties": False,
        },
    },
    {
        "name": "define_filter",
        "description": (
            "Define a dashboard filter. type 'multi' is a multi-select over data "
            "values: 'column' is the column name the filter constrains and "
            "'options_sql' returns its choices (SELECT DISTINCT ... ORDER BY); pass "
            "options as []. type 'single' is an exclusive toggle (e.g. '€ / boxes') "
            "whose selected option is substituted literally into chart SQL: pass the "
            "choices in 'options' as valid SQL fragments (e.g. column names), with "
            "options_sql '' and column ''. Charts opt in by placing the token "
            "{{filter_id}} in their SQL. Defining a filter with an existing id "
            "replaces it."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                "label": {"type": "string"},
                "type": {"type": "string", "enum": ["multi", "single"]},
                "column": {"type": "string"},
                "options_sql": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "label", "type", "column", "options_sql", "options"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_chart",
        "description": (
            "Edit an existing dashboard chart by id: fix its SQL, wire it to "
            "filters via {{filter_id}} tokens, change type/fields/title/insight. "
            "Use this to keep ALL charts responding to the global filters — "
            "especially right after defining a new filter."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "title": {"type": "string"},
                "chart_type": {"type": "string", "enum": ["bar", "line", "area", "pie", "scatter", "table"]},
                "sql": {"type": "string"},
                "x_field": {"type": "string"},
                "y_fields": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
                "insight": {"type": "string"},
            },
            "required": ["id", "title", "chart_type", "sql", "x_field", "y_fields", "insight"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete_chart",
        "description": "Remove a chart from the dashboard by id.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "define_view",
        "description": (
            "Create or replace a semantic VIEW in the project database — the "
            "stable interface between raw uploaded tables and the dashboard. "
            "Views unify/unpivot/rename raw data into clean business columns "
            "(e.g. v_sales with month/rep/product/channel/revenue/units, named in the UI language). "
            "ALL charts and filters must query views, never raw tables — so when "
            "new files arrive you only update the view and everything keeps "
            "working. name must start with 'v_'; sql is the SELECT body."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "pattern": "^v_[a-z0-9_]+$"},
                "sql": {"type": "string"},
                "description": {"type": "string",
                                "description": "One line: what this view represents, in the UI language."},
            },
            "required": ["name", "sql", "description"],
            "additionalProperties": False,
        },
    },
    {
        "name": "drop_view",
        "description": "Remove a semantic view that nothing references any more.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "pattern": "^v_[a-z0-9_]+$"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "verify_dashboard",
        "description": (
            "Run the automated health-check of the whole dashboard: executes every "
            "chart under real filter selections, validates declared fields, detects "
            "duplicate/dead/unused filters. MANDATORY as your last tool call in any "
            "turn that created or changed charts or filters — fix every reported "
            "error and re-run until ok:true before writing your final reply."
        ),
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [],
                         "additionalProperties": False},
    },
    {
        "name": "present_questions",
        "description": (
            "Present your questions to the user as an interactive form with "
            "clickable suggested answers (plus a free-text 'other' option the UI "
            "adds automatically). ALWAYS use this instead of writing questions as "
            "plain text — whenever you need to ask the user anything: clarifying "
            "the data, what they want on the dashboard, choices between options. "
            "1-4 questions per call; each with 2-4 short, concrete suggested "
            "options drawn from what you actually see in their data. Keep your "
            "accompanying text reply short — the questions carry the detail."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1, "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"},
                                        "minItems": 2, "maxItems": 6},
                            "multi": {
                                "type": "boolean",
                                "description": "true when several answers can apply at once (multi-select)",
                            },
                        },
                        "required": ["question", "options", "multi"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["questions"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_chart",
        "description": (
            "Add a chart to the user's dashboard. The SQL is executed server-side and "
            "its result rows feed the chart. x_field and y_fields must be column "
            "names (or aliases) produced by the SQL. Aggregate in SQL so the result "
            "has one row per x value (a few hundred rows max). For 'pie', y_fields "
            "has exactly one entry and there should be at most 6 slices — otherwise "
            "use a bar chart. For 'table', x_field and y_fields list the columns to "
            "display. Never create a chart with two different value scales; make two "
            "charts instead. The dashboard is dynamic: put {{filter_id}} tokens in "
            "the SQL (inside WHERE for multi filters; as the substituted fragment "
            "for single filters) so the chart responds to the dashboard filters — "
            "every filter change re-runs the SQL live."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "chart_type": {"type": "string", "enum": ["bar", "line", "area", "pie", "scatter", "table"]},
                "sql": {"type": "string"},
                "x_field": {"type": "string"},
                "y_fields": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
                "insight": {
                    "type": "string",
                    "description": "One-sentence business takeaway from this chart, stated with the actual numbers.",
                },
            },
            "required": ["title", "chart_type", "sql", "x_field", "y_fields", "insight"],
            "additionalProperties": False,
        },
    },
]

TOOL_DESC = {t["name"]: t["description"] for t in TOOLS}


def execute_tool(proj: Project, name: str, tool_input: dict) -> tuple:
    """Returns (content, is_error)."""
    t0 = time.monotonic()
    content, is_error = _execute_tool_inner(proj, name, tool_input)
    ms = int((time.monotonic() - t0) * 1000)
    status = "ERROR" if is_error else "ok"
    detail = _short(tool_input.get("sql") or tool_input.get("note")
                    or tool_input.get("id") or "")
    log.info(f"[{proj.id}] tool {name} [{status}, {ms}ms] {detail}"
             + (f" -> {_short(content, 100)}" if is_error or name != "run_sql_query" else ""))
    L = proj.lang
    if name == "verify_dashboard":
        proj.log_activity("info", T(L, "act_verify",
                                    status=T(L, "act_verify_err" if is_error else "act_verify_ok")))
    elif is_error and name == "run_sql_query":
        proj.log_activity("sql", T(L, "act_sql_retry"))
    elif is_error:
        proj.log_activity("error", T(L, "act_tool_error", name=name, detail=_short(content, 90)))
    elif name == "run_sql_query":
        proj.log_activity("sql", T(L, "act_sql_look", sql=_short(tool_input.get('sql', ''), 80)))
    elif name == "record_data_context":
        proj.log_activity("note", T(L, "act_note", note=_short(tool_input.get('note', ''), 80)))
    elif name == "define_filter":
        proj.log_activity("filter", T(L, "act_filter", label=tool_input.get('label', '')))
    elif name == "define_view":
        proj.log_activity("info", T(L, "act_view", name=tool_input.get('name', ''),
                                    desc=_short(tool_input.get('description', ''), 60)))
    elif name == "drop_view":
        proj.log_activity("info", T(L, "act_view_drop", name=tool_input.get('name', '')))
    elif name == "create_chart":
        proj.log_activity("chart", T(L, "act_chart", title=_short(tool_input.get('title', ''), 60)))
    elif name == "update_chart":
        proj.log_activity("chart", T(L, "act_chart_upd", title=_short(tool_input.get('title', ''), 60)))
    elif name == "delete_chart":
        proj.log_activity("chart", T(L, "act_chart_del", id=tool_input.get('id')))
    elif name == "present_questions":
        proj.log_activity("info", T(L, "act_questions", n=len(tool_input.get('questions', []))))
    return content, is_error


def _execute_tool_inner(proj: Project, name: str, tool_input: dict) -> tuple:
    try:
        if name == "record_data_context":
            proj.notes.append(tool_input["note"])
            proj.save_notes()
            return "Saved.", False

        if name == "define_view":
            vname, body = tool_input["name"], tool_input["sql"].strip().rstrip(";")
            if FORBIDDEN_SQL.search(body):
                return "Error: the view body must be a plain SELECT.", True
            if not db.has_data(proj.id):
                return "Error: the project has no data yet.", True
            try:
                db.create_view(proj.id, vname, pg_compat(body))
            except Exception as e:
                return f"Error: the view could not be created — {str(e).splitlines()[0]}", True
            df = run_readonly_sql(proj, f'SELECT * FROM "{vname}" LIMIT 3', 3)
            proj.meta.setdefault("views", {})[vname] = tool_input["description"]
            proj.save_meta()
            return (f"View '{vname}' created: columns {list(df.columns)}, "
                    f"sample ok."), False

        if name == "drop_view":
            vname = tool_input["name"]
            try:
                db.drop_view(proj.id, vname)
            except Exception as e:
                return f"Error: {str(e).splitlines()[0]}", True
            proj.meta.get("views", {}).pop(vname, None)
            proj.save_meta()
            return f"View '{vname}' dropped.", False

        if name == "verify_dashboard":
            report = verify_dashboard(proj)
            return json.dumps(report, ensure_ascii=False), not report["ok"]

        if name == "present_questions":
            proj.new_questions = tool_input["questions"]
            return ("Questions presented to the user as an interactive form. Now "
                    "finish your reply with a short intro text — do NOT repeat the "
                    "questions in it."), False

        if name == "run_sql_query":
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, tool_input["sql"], {}),
                                  MAX_PREVIEW_ROWS)
            return json.dumps({"row_count": len(df), "rows": frame_to_records(df)}), False

        if name == "define_filter":
            f = {k: tool_input[k] for k in ("id", "label", "type", "column", "options_sql", "options")}
            opts = resolve_filter_options(proj, f)
            if not opts:
                return (f"Error: filter '{f['id']}' resolves to no options — check "
                        "options_sql/options."), True
            proj.filters[:] = [x for x in proj.filters if x["id"] != f["id"]] + [f]
            proj.save_filters()
            return f"Filter '{f['id']}' defined with {len(opts)} options: {opts[:12]}", False

        if name == "delete_chart":
            before = len(proj.dashboard)
            proj.dashboard[:] = [c for c in proj.dashboard if c["id"] != tool_input["id"]]
            if len(proj.dashboard) == before:
                return f"Error: no chart with id {tool_input['id']}.", True
            proj.save_dash()
            return f"Chart #{tool_input['id']} deleted.", False

        if name == "update_chart":
            chart = next((c for c in proj.dashboard if c["id"] == tool_input["id"]), None)
            if chart is None:
                return (f"Error: no chart with id {tool_input['id']}. Existing ids: "
                        f"{[c['id'] for c in proj.dashboard]}"), True
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, tool_input["sql"], {}),
                                  MAX_CHART_ROWS)
            missing = [f for f in [tool_input["x_field"], *tool_input["y_fields"]]
                       if f not in df.columns]
            if missing:
                return (f"Error: field(s) {missing} not in query result. "
                        f"Available columns: {list(df.columns)}"), True
            chart.update({k: tool_input[k] for k in
                          ("title", "chart_type", "sql", "x_field", "y_fields", "insight")})
            chart["rows"] = frame_to_records(df)
            proj.save_dash()
            return f"Chart #{chart['id']} updated ({len(df)} rows).", False

        if name == "create_chart":
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, tool_input["sql"], {}),
                                  MAX_CHART_ROWS)
            missing = [f for f in [tool_input["x_field"], *tool_input["y_fields"]]
                       if f not in df.columns]
            if missing:
                return (f"Error: field(s) {missing} not in query result. "
                        f"Available columns: {list(df.columns)}"), True
            proj.chart_seq += 1
            chart = {
                "id": proj.chart_seq,
                "title": tool_input["title"],
                "chart_type": tool_input["chart_type"],
                "sql": tool_input["sql"],
                "x_field": tool_input["x_field"],
                "y_fields": tool_input["y_fields"],
                "insight": tool_input["insight"],
                "rows": frame_to_records(df),
            }
            proj.new_charts.append(chart)
            proj.dashboard.append(chart)
            proj.save_dash()
            return f"Chart #{proj.chart_seq} '{chart['title']}' created with {len(df)} rows.", False

        return f"Unknown tool: {name}", True
    except Exception as e:  # surface DB/SQL errors to the model so it can retry
        return f"Error: {e}", True


# ------------------------------------------------------------- system prompt

PROMPT_INTRO = """You are the analytics copilot inside a dashboard product for non-technical
sales and business users. The user's uploaded spreadsheets live in a PostgreSQL
database (one schema per project; you only see this project's tables). You answer questions and build dashboard charts for them."""

PROMPT_INTERVIEW = """The interview (how a new dataset becomes a dashboard):

Step 1 — understand the data. When files are newly uploaded, first investigate
them yourself with run_sql_query: distinct values of categorical/code columns,
date ranges, row counts, obvious keys between tables. Then tell the user in
2-4 plain sentences what you believe the data represents. If (and only if)
something you genuinely could not figure out matters for analysis — cryptic
codes or SKUs, ambiguous columns, units/currency, how tables relate — ask
about it. Never ask about things that are obvious or already in memory.

Step 2 — understand what the user wants: what decisions or meetings the
dashboard is for; which metrics matter most; what comparisons they care about
(over time, by person, by product, vs target); any specific views they
imagine.

HOW to ask (steps 1 and 2, and any later question): ALWAYS use the
present_questions tool — never write questions as plain text. Combine the
data questions and the goal questions into ONE present_questions call (max 4
questions total). Give each question 2-6 short suggested options based on
what you actually see in THEIR data (your best guesses first — e.g. for
currency: "Euro (€)", "Lev (BGN)"); the UI automatically adds a free-text
"other answer" option. Questions and options are written in the UI language
(see the Output language rule). Set multi=true whenever several answers can
apply at once (e.g. "which comparisons matter to you", "which metrics to
track") — the
user then picks multiple; keep multi=false for exclusive choices (currency,
fiscal year). Your text reply should be only the short summary of
what you understood — the form carries the questions.

Step 3 — build. Once the user answers, save every durable fact AND every
stated preference/goal with record_data_context (one short note per fact, in
their terms), then build without asking for permission:
1. First build the semantic layer with define_view — clean v_* views over the
   raw tables (see the two-layer rule below).
2. Then define the dashboard filters with define_filter over the views — the
   dimensions the user will want to slice by (time period, person,
   product/group, channel, chain...), plus a 'single' metric toggle when both
   value and volume exist.
3. Then create the charts with create_chart querying ONLY the views, wiring
   every chart to the relevant filters via {{filter_id}} tokens so the whole
   dashboard responds to filter changes.
A good first dashboard follows the Dashboard UX standard below: the summary
table on top, 4-6 charts, 3-6 canonical filters. After building, offer 1-2
ideas for what could be added next.

The user's stated goal is a floor, not a ceiling: even when they told you
upfront what they want, still investigate the data yourself — and when you
discover something valuable beyond the brief (a trend, anomaly, risk or
opportunity), say it with the numbers and OFFER to add the view for it.
Propose, don't add unasked.

At any later point: if the user just asks a question or requests a chart,
answer/build directly — the interview is only for new or unclear situations.
Never ask the same thing twice; check memory first.

Memory is the project's knowledge base: record with record_data_context not
only the user's answers, but also YOUR OWN important discoveries from
investigating the data (how tables join, name mismatches between sources,
date quirks, canonical mappings, computed baselines worth reusing). This is
what lets any future session continue without re-analysis."""

PROMPT_RULES = f"""Data architecture — the two-layer rule (apply ALWAYS):
- Raw uploaded tables are a LANDING ZONE only. Before building any dashboard,
  create semantic VIEWS with define_view (names v_*): they unify, unpivot and
  rename the raw data into clean business columns in the UI language
  (e.g. v_sales: month, rep, product, channel, revenue, units — in __LANGUAGE__).
- ALL charts and filters query ONLY views, never raw tables. That is what
  keeps the dashboard alive when new files arrive.
- When new files are uploaded, FIRST update the affected view definitions so
  they include the new data (same view name, same columns), then run
  verify_dashboard — existing charts must keep working without edits.
- If a raw table is replaced or removed, fix the views, not the charts.
- Keep the semantic layer small: 1-4 views with clear one-line descriptions.

Dashboard UX standard — apply in EVERY project, without being asked:
- Composition: the FIRST chart is always a 'table' summary ("Summary:
  observations and recommendations", in __LANGUAGE__) whose rows carry theme / the actual number /
  observation / concrete recommendation, built from filter-aware SQL so it
  recalculates with the filters. Then 4-8 charts that together cover: trend
  over time, ranking of people/entities, structure (groups/channels/share),
  execution vs target when targets exist, and a detail table at the end.
- Filters: ONE canonical, minimal set — NEVER two filters for the same
  dimension. If a similar filter already exists, redefine it under the SAME id
  instead of creating a parallel one; a replaced or unused filter must not be
  left behind. Typical set: time period, person, product/group,
  channel/segment, plus a 'single' metric toggle when both value and volume
  exist.
- Labels: business language, in the UI language (__LANGUAGE__), everywhere — chart
  titles, SQL result aliases (they become axis/table labels), filter labels.
  Never expose raw column names. Months in chronological/fiscal order, never
  alphabetical.
- Label readability is non-negotiable: rankings and any category axis with
  long names (people, products) belong on BAR charts — the renderer flips
  them horizontal automatically so names never collide. Keep category counts
  chart-friendly: top-N (10-15) with the rest folded into 'Other' instead of
  50 unreadable slivers; short category values in SQL (e.g. 'Oct' not
  '2024-10-01 00:00:00').
- Insights: every chart's insight states the actual numbers and what to do
  about them — it is the sentence the user will paste into their report.
- Work incrementally: build and rewire in small batches (a few charts per
  response), keeping the dashboard consistent after every step — never a
  single giant rebuild that can be cut off half-way.
- VERIFY BEFORE DONE (mandatory): in every turn where you created or changed
  charts or filters, your LAST tool call must be verify_dashboard. If it
  reports errors — fix them (update_chart / define_filter / delete_chart) and
  run it again, until ok:true. Never tell the user the dashboard is ready
  without a clean verification; mention in one short line that the check
  passed.

Dynamic dashboards (filters):
- The dashboard is live: whenever the user changes a filter, every chart's SQL
  re-runs against the database with the new selections.
- 'multi' filters: the token {{{{filter_id}}}} expands to a boolean condition
  ("column" IN (...)), or TRUE when nothing is selected — so place it inside
  WHERE, e.g. WHERE {{{{months}}}} AND {{{{reps}}}}. The filter's declared
  column must exist under that exact name in the tables/subquery the chart
  queries (alias it if needed).
- 'single' filters: the token is replaced by the selected option text — use
  for metric toggles, e.g. SUM({{{{metric}}}}) with options ["revenue",
  "units_sold"]. Options must be valid SQL fragments.
- run_sql_query also accepts these tokens (expanded with default selections),
  so you can test a templated query before charting it.
- EVERY chart must be wired via {{tokens}} to ALL global filters that
  logically apply to its data (time period, person, product, channel, metric
  toggle...). A chart that ignores the dashboard filters is a bug.
- When you define a NEW filter, immediately wire it into every existing chart
  it should affect using update_chart. Use update_chart to fix charts and
  delete_chart to remove obsolete ones.

Rules:
- Write PostgreSQL SQL. Quote identifiers with double quotes. Aggregate in SQL —
  the chart receives at most {MAX_CHART_ROWS} rows, so group and order the data
  so each x value appears once.
- PostgreSQL specifics: every non-aggregated SELECT column must appear in GROUP BY
  (positional "GROUP BY 1, 2" is fine); cast explicitly ("col"::numeric,
  "col"::text, NULLIF(x, '')::double precision for text numbers); integer / integer
  truncates — cast to numeric first; ROUND(x::numeric, 1); text concatenation with
  ||; date_trunc('month', d), EXTRACT(year FROM d), to_char(d, 'YYYY-MM');
  string_agg(x, ', ' ORDER BY x); percentile_cont(0.5) WITHIN GROUP (ORDER BY x);
  mode() WITHIN GROUP (ORDER BY x); FILTER (WHERE …) on aggregates; no TRY_CAST
  (use CASE WHEN x ~ '^-?[0-9.]+$' THEN x::numeric END); no list_/struct functions;
  LIMIT/OFFSET as usual. One statement per query, SELECT/WITH only.
- Use run_sql_query first when you are unsure about values or need to explore;
  use create_chart to put results on the dashboard.
- Pick the chart form by the data's job: change over time -> line or area;
  comparing categories -> bar (sorted by value unless the x axis is ordered,
  e.g. months); share of a small whole (<= 6 slices) -> pie, otherwise bar;
  relationship between two measures -> scatter; detailed records -> table.
- Never mix two different value scales in one chart; create two charts instead.
- At most {MAX_SERIES} series per chart; fold small categories into 'Other'.
- The user is not technical: never show SQL or column jargon in your replies.
  Speak in plain business language, brief and concrete, and mention the actual
  numbers you found.
- Output language: the UI language is __LANGUAGE__. EVERYTHING you produce
  for the user — chat replies, interview questions and options, chart titles,
  insights, filter labels, view descriptions, SQL result aliases, notes and
  presentation content — must be in __LANGUAGE__, regardless of the language
  of the source data or of the user's message, unless the user explicitly
  asks for another language. Data VALUES stay exactly as they are in the data.
- If the request is ambiguous, make a sensible choice and state it in one line
  rather than asking questions.
- If there is no uploaded data yet, tell the user to upload a file first."""


def prompt_rules(lang: str) -> str:
    """PROMPT_RULES with the UI language name filled in."""
    return PROMPT_RULES.replace("__LANGUAGE__", LANG_NAMES.get(lang, LANG_NAMES["bg"]))


def build_system_prompt(proj: Project) -> str:
    schema = json.dumps(describe_schema(proj), default=str)
    notes = "\n".join(f"- {n}" for n in proj.notes) or "(nothing recorded yet)"
    return f"""{PROMPT_INTRO}

Current database schema (tables, column types, sample rows):
{schema}

What you have learned about this data from the user (permanent memory):
{notes}

{PROMPT_INTERVIEW}

{prompt_rules(proj.lang)}"""


# ------------------------------------------- subscription backend (Agent SDK)

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

# The SDK MCP tool functions are module-level, so the project a turn operates
# on is bound here. AGENT_LOCK serializes all agent turns process-wide, which
# both prevents interleaving on one SDK session and keeps this binding safe.
CURRENT_PROJECT: Project | None = None
AGENT_LOCK: asyncio.Lock | None = None


def _mcp_result(content: str, is_error: bool) -> dict:
    prefix = "Error: " if is_error and not content.startswith("Error") else ""
    return {"content": [{"type": "text", "text": prefix + content}]}


@tool("run_sql_query", TOOL_DESC["run_sql_query"], {"sql": str})
async def sdk_run_sql(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "run_sql_query", args))


@tool("record_data_context", TOOL_DESC["record_data_context"], {"note": str})
async def sdk_record_note(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "record_data_context", args))


@tool("define_filter", TOOL_DESC["define_filter"], {
    "id": str, "label": str, "type": str,
    "column": str, "options_sql": str, "options": list,
})
async def sdk_define_filter(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "define_filter", args))


@tool("create_chart", TOOL_DESC["create_chart"], {
    "title": str, "chart_type": str, "sql": str,
    "x_field": str, "y_fields": list, "insight": str,
})
async def sdk_create_chart(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "create_chart", args))


@tool("update_chart", TOOL_DESC["update_chart"], {
    "id": int, "title": str, "chart_type": str, "sql": str,
    "x_field": str, "y_fields": list, "insight": str,
})
async def sdk_update_chart(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "update_chart", args))


@tool("delete_chart", TOOL_DESC["delete_chart"], {"id": int})
async def sdk_delete_chart(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "delete_chart", args))


@tool("define_view", TOOL_DESC["define_view"], {"name": str, "sql": str, "description": str})
async def sdk_define_view(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "define_view", args))


@tool("drop_view", TOOL_DESC["drop_view"], {"name": str})
async def sdk_drop_view(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "drop_view", args))


@tool("verify_dashboard", TOOL_DESC["verify_dashboard"], {})
async def sdk_verify_dashboard(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "verify_dashboard", args or {}))


@tool("present_questions", TOOL_DESC["present_questions"], {"questions": list})
async def sdk_present_questions(args):
    return _mcp_result(*execute_tool(CURRENT_PROJECT, "present_questions", args))


ANALYTICS_SERVER = create_sdk_mcp_server(
    name="analytics",
    tools=[sdk_run_sql, sdk_record_note, sdk_define_filter, sdk_create_chart,
           sdk_update_chart, sdk_delete_chart, sdk_define_view, sdk_drop_view,
           sdk_verify_dashboard, sdk_present_questions],
)


def sub_options(proj: Project) -> ClaudeAgentOptions:
    # Static rules only — the live schema and learned facts are injected at the
    # top of every user message, since a persistent session's system prompt
    # cannot change after connect.
    rules = f"""{PROMPT_INTRO}

The current database schema and everything you have learned about the data are
provided in a <data_context> block at the top of every user message — always
use the latest one. Use ONLY the analytics tools (run_sql_query,
record_data_context, define_view, drop_view, define_filter, create_chart,
update_chart, delete_chart, verify_dashboard, present_questions).
chart_type must be one of: bar, line, area, pie, scatter, table; y_fields is
a list of column names (max 8). define_filter's type is 'multi' or 'single';
pass unused fields as '' / []. present_questions takes
{{"questions": [{{"question": str, "options": [str, ...]}}]}}.

{PROMPT_INTERVIEW}

{prompt_rules(proj.lang)}"""
    return ClaudeAgentOptions(
        system_prompt=rules,
        mcp_servers={"analytics": ANALYTICS_SERVER},
        allowed_tools=[
            "mcp__analytics__run_sql_query",
            "mcp__analytics__record_data_context",
            "mcp__analytics__define_filter",
            "mcp__analytics__create_chart",
            "mcp__analytics__update_chart",
            "mcp__analytics__delete_chart",
            "mcp__analytics__define_view",
            "mcp__analytics__drop_view",
            "mcp__analytics__verify_dashboard",
            "mcp__analytics__present_questions",
        ],
        disallowed_tools=[
            "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch",
            "WebFetch", "NotebookEdit", "Task", "TodoWrite",
        ],
        permission_mode="bypassPermissions",
        setting_sources=[],
        max_turns=40,
        cwd=str(proj.dir),
    )


async def run_agent_subscription(proj: Project, user_content: str):
    global CURRENT_PROJECT, AGENT_LOCK
    if AGENT_LOCK is None:
        AGENT_LOCK = asyncio.Lock()

    async with AGENT_LOCK:
        CURRENT_PROJECT = proj
        proj.new_charts.clear()
        proj.new_questions = []
        recap = ""
        if proj.sub_client is not None and proj.sub_lang != proj.lang:
            # the system prompt (incl. output language) is fixed at connect time
            log.info(f"[{proj.id}] agent[subscription]: UI language changed "
                     f"{proj.sub_lang} -> {proj.lang}, reconnecting SDK session")
            try:
                await proj.sub_client.disconnect()
            except Exception:
                pass
            proj.sub_client = None
        if proj.sub_client is None:
            proj.sub_client = ClaudeSDKClient(options=sub_options(proj))
            await proj.sub_client.connect()
            proj.sub_lang = proj.lang
            recap = conversation_recap(proj)
            log.info(f"[{proj.id}] agent[subscription]: new SDK session connected"
                     + (" (with conversation recap)" if recap else ""))
            proj.log_activity("info", T(proj.lang, "act_new_session")
                              + (T(proj.lang, "act_session_recap") if recap else ""))

        ctx: dict = {"schema": describe_schema(proj), "known_facts": proj.notes}
        bf = brand_files(proj)
        if bf:
            ctx["brand"] = {"files": bf, "brandbook_excerpt": brand_excerpt(proj, 1500)}
        context = json.dumps(ctx, default=str, ensure_ascii=False)
        try:
            async with asyncio.timeout(SUB_TIMEOUT_S):
                await proj.sub_client.query(
                    f"{recap}<data_context>\n{context}\n</data_context>\n\n{user_content}"
                )
                reply = ""
                async for message in proj.sub_client.receive_response():
                    if isinstance(message, AssistantMessage):
                        text = "".join(b.text for b in message.content if isinstance(b, TextBlock))
                        if text.strip():
                            reply = text  # keep the last non-empty assistant text
                    elif isinstance(message, ResultMessage):
                        if message.is_error and not reply:
                            raise HTTPException(502, T(proj.lang, "err_ai_sub_failed",
                                                       detail=message.result))
                        break
        except (TimeoutError, asyncio.TimeoutError):
            # Session state unknown — drop it so the next turn starts fresh
            try:
                await proj.sub_client.disconnect()
            except Exception:
                pass
            proj.sub_client = None
            raise HTTPException(504, T(proj.lang, "err_ai_timeout"))
        return {"reply": reply, "charts": list(proj.new_charts),
                "questions": list(proj.new_questions),
                "tables": describe_schema(proj), "notes": proj.notes}


def run_agent_api(proj: Project, user_content: str):
    """Production path: Anthropic API with a manual tool loop."""
    if not proj.messages:  # fresh process: continue from the stored transcript
        user_content = conversation_recap(proj) + user_content
    proj.messages.append({"role": "user", "content": user_content})
    proj.new_charts.clear()
    proj.new_questions = []

    while True:
        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{
                    "type": "text",
                    "text": build_system_prompt(proj),
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=TOOLS,
                messages=proj.messages,
            )
        except anthropic.APIStatusError as e:
            if proj.messages and proj.messages[-1]["role"] == "user":
                proj.messages.pop()
            raise HTTPException(502, T(proj.lang, "err_ai_failed", detail=e.message))
        except anthropic.APIConnectionError:
            raise HTTPException(502, T(proj.lang, "err_ai_unreachable"))

        # Keep full content blocks (incl. thinking) so multi-step turns replay correctly
        proj.messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            reply = T(proj.lang, "err_ai_refusal")
            return {"reply": reply, "charts": list(proj.new_charts), "questions": [],
                    "tables": describe_schema(proj), "notes": proj.notes}

        if response.stop_reason == "pause_turn":
            continue

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    content, is_error = execute_tool(proj, block.name, block.input)
                    result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    if is_error:
                        result["is_error"] = True
                    tool_results.append(result)
            proj.messages.append({"role": "user", "content": tool_results})
            continue

        reply = "".join(b.text for b in response.content if b.type == "text")
        return {"reply": reply, "charts": list(proj.new_charts),
                "questions": list(proj.new_questions),
                "tables": describe_schema(proj), "notes": proj.notes}


async def dispatch_agent(proj: Project, user_content: str):
    t0 = time.monotonic()
    log.info(f"[{proj.id}] agent[{AI_BACKEND}]: turn start — {_short(user_content, 120)}")
    proj.log_activity("info", T(proj.lang, "act_thinking"))
    try:
        result = (await run_agent_subscription(proj, user_content)
                  if AI_BACKEND == "subscription"
                  else await run_in_threadpool(run_agent_api, proj, user_content))
    except Exception as e:
        log.info(f"[{proj.id}] agent[{AI_BACKEND}]: turn FAILED after "
                 f"{time.monotonic() - t0:.1f}s — {_short(e, 160)}")
        raise
    log.info(f"[{proj.id}] agent[{AI_BACKEND}]: turn done in {time.monotonic() - t0:.1f}s — "
             f"{len(result['charts'])} new chart(s), {len(proj.filters)} filter(s), "
             f"{len(proj.notes)} note(s) in memory; reply: {_short(result['reply'], 110)}")
    proj.add_chat("ai", result["reply"], questions=result.get("questions") or None)
    write_progress(proj)
    return result


# ------------------------------------------------------------ project routes

class ProjectCreate(BaseModel):
    name: str


@app.get("/api/projects")
def list_projects():
    out = []
    for pdir in sorted(PROJECTS_DIR.iterdir()):
        if not pdir.is_dir():
            continue
        try:
            proj = get_project(pdir.name)
            out.append({
                "id": proj.id,
                "name": proj.meta.get("name", proj.id),
                "created": proj.meta.get("created", ""),
                "tables": len(describe_schema(proj)),
                "charts": len(proj.dashboard),
                "notes": len(proj.notes),
            })
        except Exception:
            continue
    return {"projects": out}


@app.post("/api/projects")
def create_project(req: ProjectCreate, request: Request):
    name = req.name.strip() or T(req_lang(request), "new_project")
    # project ids are ASCII URL slugs; non-Latin names fall back to a random id
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or f"project-{uuid.uuid4().hex[:6]}"
    pid = slug if not (PROJECTS_DIR / slug).exists() else f"{slug}-{uuid.uuid4().hex[:6]}"
    (PROJECTS_DIR / pid).mkdir(parents=True)
    db.ensure_project(pid)
    proj = get_project(pid)
    proj.meta["name"] = name
    proj.save_meta()
    write_progress(proj)
    log.info(f"[{pid}] project created: '{name}'")
    return {"id": pid, "name": name}


@app.put("/api/projects/{pid}")
def rename_project(pid: str, req: ProjectCreate):
    proj = get_project(pid)
    name = req.name.strip()
    if name:
        proj.meta["name"] = name
        proj.save_meta()
        log.info(f"[{pid}] project renamed to '{name}'")
    return {"id": pid, "name": proj.meta["name"]}


@app.delete("/api/projects/{pid}")
async def delete_project(pid: str):
    proj = get_project(pid)
    if proj.sub_client is not None:
        try:
            await proj.sub_client.disconnect()
        except Exception:
            pass
    PROJECTS.pop(pid, None)
    shutil.rmtree(proj.dir, ignore_errors=True)
    try:
        db.drop_project(pid)
    except Exception as e:
        log.info(f"[{pid}] drop schema failed — {_short(e)}")
    log.info(f"[{pid}] project deleted")
    return {"ok": True}


# ----------------------------------------------------- project-scoped routes

class ChatRequest(BaseModel):
    message: str


class ReviewRequest(BaseModel):
    tables: list[str]
    context: str = ""   # optional: what the user already knows about the data
    goal: str = ""      # optional: what they want to achieve


@app.get("/api/p/{pid}/verify")
def verify_endpoint(pid: str):
    return verify_dashboard(get_project(pid))


class RefreshRequest(BaseModel):
    selections: dict


class NoteRequest(BaseModel):
    note: str



# ------------------------------------------------- content localization
# Dashboards are written by the AI in the UI language of the moment. When the
# user switches language, every text the dashboard carries (chart titles,
# insights, filter labels, notes, field names, textual values) is translated
# ONCE by the AI and cached in the project (i18n_<lang>.json, keyed by a hash
# of the source text so edits invalidate only what changed). /state serves
# the translated view; the frontend maps field/value labels at render time.

def _cyr_ratio(texts) -> float:
    s = " ".join(t for t in texts if isinstance(t, str))
    letters = [ch for ch in s if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ") / len(letters)


def content_lang(proj: Project) -> str:
    texts = [c.get("title", "") for c in proj.dashboard] + [f.get("label", "") for f in proj.filters]
    if not texts:
        return "bg"
    return "bg" if _cyr_ratio(texts) > 0.5 else "en"


def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def _i18n_path(proj: Project, lang: str) -> Path:
    return proj.dir / f"i18n_{lang}.json"


def _load_i18n(proj: Project, lang: str) -> dict:
    p = _i18n_path(proj, lang)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _has_letters(v) -> bool:
    return isinstance(v, str) and any(ch.isalpha() for ch in v) and not v.strip().isdigit()


def translatable_items(proj: Project, lang: str | None = None) -> dict:
    """Every source text of the project that the UI shows, keyed by hash."""
    items: dict = {}

    def add(text):
        if _has_letters(text) and len(text) <= 1200:
            items[_h(text)] = text
    for c in proj.dashboard:
        add(c.get("title", ""))
        add(c.get("insight", ""))
        add(c.get("x_field", ""))
        for y in c.get("y_fields", []) or []:
            add(y)
        n = 0
        for r in c.get("rows") or []:
            for v in r.values():
                if _has_letters(v) and n < 400:
                    add(v)
                    n += 1
    for f in proj.filters:
        add(f.get("label", ""))
        for o in (f.get("options") or [])[:60]:
            if isinstance(o, dict):
                add(o.get("label", ""))
            else:
                add(o)
    for n in proj.notes:
        add(n)
    for v in (proj.meta.get("views") or {}).values():
        if isinstance(v, dict):
            add(v.get("description", ""))
    # textual values first seen in filtered re-runs (see localize_charts)
    for v in list(getattr(proj, "i18n_pending", {}).get(lang, set()) if lang else []):
        add(v)
    return items


def localize_charts(proj: Project, lang: str, tr: dict, charts: list):
    """Translate title/insight and every textual cell of the given charts with
    the cached map. Values without a translation are queued so the next
    /translate run picks them up (filters reveal values the stored sample
    did not contain). Returns (charts, field_labels, value_labels, pending)."""
    if not hasattr(proj, "i18n_pending"):
        proj.i18n_pending = {}
    pending = proj.i18n_pending.setdefault(lang, set())
    fields, values = {}, {}
    out = []
    for c in charts:
        cc = dict(c)
        for k in ("title", "insight"):
            if _has_letters(c.get(k)):
                cc[k] = tr.get(_h(c[k]), c[k])
        for name in [c.get("x_field", "")] + list(c.get("y_fields") or []):
            if _has_letters(name) and _h(name) in tr:
                fields[name] = tr[_h(name)]
        for r in c.get("rows") or []:
            for v in r.values():
                if _has_letters(v):
                    t = tr.get(_h(v))
                    if t is not None:
                        values[v] = t
                    elif len(pending) < 600 and v not in pending and len(v) <= 1200:
                        pending.add(v)
        out.append(cc)
    return out, fields, values, pending


def localized_content(proj: Project, lang: str):
    """(charts, notes, filters, i18n_info) for the UI language."""
    src = content_lang(proj)
    filters = filters_with_options(proj)
    info = {"content_lang": src, "ui_lang": lang, "needs_translation": False,
            "field_labels": {}, "value_labels": {}}
    if lang == src or (not proj.dashboard and not proj.notes):
        return proj.dashboard, proj.notes, filters, info
    tr = _load_i18n(proj, lang)
    charts, info["field_labels"], info["value_labels"], _ = localize_charts(proj, lang, tr, proj.dashboard)
    items = translatable_items(proj, lang)
    missing = [k for k in items if k not in tr]
    info["needs_translation"] = bool(missing)
    info["missing"] = len(missing)

    def tx(text):
        return tr.get(_h(text), text) if isinstance(text, str) else text
    fl = []
    for f in filters:
        ff = dict(f)
        ff["label"] = tx(f.get("label", ""))
        fl.append(ff)
        for o in (f.get("options") or []):
            lab = o.get("label") if isinstance(o, dict) else o
            if _has_letters(lab) and _h(lab) in tr:
                info["value_labels"][lab] = tr[_h(lab)]
    notes = [tx(n) for n in proj.notes]
    return charts, notes, fl, info


TRANSLATE_PROMPT = """[Task: translate the user-facing texts of this dashboard into {language}.
These are chart titles, insights, filter labels, field names, category values and
analyst notes from the current project — use the project context you know for
correct business terminology. Rules: keep numbers, units, currency codes, product
and company names, SKUs and abbreviations exactly as they are; keep the tone and
length (a field name stays a short field name); translate category values
consistently (the same source text always gets the same translation); never add
commentary; do not run tools. Return ONLY valid JSON: an object mapping each key
to its translation, with exactly the same keys as the input.

Input:
{payload}]"""


@app.post("/api/p/{pid}/translate")
async def translate_content(pid: str, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    src = content_lang(proj)
    if lang == src:
        return {"translated": 0, "content_lang": src}
    tr = _load_i18n(proj, lang)
    items = translatable_items(proj, lang)
    missing = {k: v for k, v in items.items() if k not in tr}
    if not missing:
        return {"translated": 0, "content_lang": src}
    log.info(f"[{pid}] i18n: translating {len(missing)} texts -> {lang}")
    proj.log_activity("info", T(lang, "act_translating", n=len(missing)))
    done = 0
    keys = list(missing)
    # chunks keep each model answer comfortably parseable
    for i in range(0, len(keys), 80):
        chunk = {k: missing[k] for k in keys[i:i + 80]}
        prompt = TRANSLATE_PROMPT.format(language=LANG_NAMES[lang],
                                         payload=json.dumps(chunk, ensure_ascii=False))
        result = (await run_agent_subscription(proj, prompt)
                  if AI_BACKEND == "subscription"
                  else await run_in_threadpool(run_agent_api, proj, prompt))
        raw = result["reply"].strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            log.info(f"[{pid}] i18n: chunk {i // 80 + 1} — no JSON in reply")
            continue
        try:
            got = json.loads(m.group(0))
        except Exception:
            log.info(f"[{pid}] i18n: chunk {i // 80 + 1} — invalid JSON")
            continue
        for k, v in got.items():
            if k in chunk and isinstance(v, str) and v.strip():
                tr[k] = v.strip()
                done += 1
        _i18n_path(proj, lang).write_text(json.dumps(tr, ensure_ascii=False, indent=1))
    pend = getattr(proj, "i18n_pending", {}).get(lang)
    if pend:
        pend.difference_update({v for v in pend if _h(v) in tr})
    # drop entries whose source text no longer exists (keeps the file small)
    tr = {k: v for k, v in tr.items() if k in items}
    _i18n_path(proj, lang).write_text(json.dumps(tr, ensure_ascii=False, indent=1))
    log.info(f"[{pid}] i18n: done — {done}/{len(missing)} translated")
    proj.log_activity("info", T(lang, "act_translated", n=done))
    return {"translated": done, "missing": len(missing) - done, "content_lang": src,
            "reply": T(lang, "act_translated", n=done)}


@app.get("/api/p/{pid}/state")
def state(pid: str, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    charts, notes, filters, i18n = localized_content(proj, lang)
    return {"name": proj.meta.get("name", pid),
            "tables": describe_schema(proj), "charts": charts,
            "notes": notes, "filters": filters, "i18n": i18n,
            "chat": proj.chat, "brand": brand_files(proj),
            "brand_theme": {
                "primary": "#%02x%02x%02x" % tuple(int(v * 255) for v in brand_theme(proj)[0]),
                "accent": "#%02x%02x%02x" % tuple(int(v * 255) for v in brand_theme(proj)[1]),
            },
            "brand_logo": (brand_logo_path(proj).name if brand_logo_path(proj) else None),
            "brand_colors": brand_colors(proj),
            "brand_fonts": (json.loads((brand_dir(proj) / "brand.json").read_text()).get("fonts", [])
                            if (brand_dir(proj) / "brand.json").exists() else []),
            "files": [{"filename": k, "tables": v} for k, v in proj.meta["files"].items()]}


@app.get("/api/p/{pid}/activity")
def activity(pid: str, since: int = 0):
    proj = get_project(pid)
    return {"events": [e for e in proj.activity if e["seq"] > since], "seq": proj.act_seq}


@app.post("/api/p/{pid}/upload")
async def upload(pid: str, request: Request, files: list[UploadFile] = File(...)):
    proj = get_project(pid)
    proj.lang = req_lang(request)
    log.info(f"[{pid}] upload: {len(files)} file(s) received")
    loaded = []
    db.ensure_project(pid)
    try:
        for f in files:
            payload = await f.read()
            fname = Path(f.filename).name
            log.info(f"[{pid}] upload: parsing '{fname}' ({len(payload) // 1024} KB)")
            (proj.uploads_dir / fname).write_bytes(payload)
            file_tables = []
            for table, df in load_frames_from_upload(fname, payload).items():
                await run_in_threadpool(db.load_frame, pid, table, df)
                loaded.append({"table": table, "rows": len(df)})
                file_tables.append(table)
                log.info(f"[{pid}] upload: table '{table}' loaded — {len(df)} rows, "
                         f"{len(df.columns)} cols: {_short(', '.join(map(str, df.columns)), 110)}")
                proj.log_activity("info", T(proj.lang, "act_table_loaded", table=table,
                                            rows=len(df), cols=len(df.columns)))
            proj.meta["files"][fname] = file_tables
    finally:
        proj.save_meta()
    log.info(f"[{pid}] upload: done — {len(loaded)} table(s), {sum(l['rows'] for l in loaded)} rows total")
    write_progress(proj)
    return {"loaded": loaded, "tables": describe_schema(proj)}


@app.delete("/api/p/{pid}/files/{filename}")
def delete_file(pid: str, filename: str):
    proj = get_project(pid)
    fname = Path(filename).name
    tables = proj.meta["files"].pop(fname, [])
    for t in tables:
        try:
            db.drop_table(pid, t)
        except Exception as e:
            log.info(f"[{pid}] drop table '{t}' failed — {_short(e)}")
    upload_file = proj.uploads_dir / fname
    if upload_file.exists():
        upload_file.unlink()
    proj.save_meta()
    write_progress(proj)
    log.info(f"[{pid}] file deleted: '{fname}' (+{len(tables)} table(s))")
    return {"ok": True, "dropped_tables": tables}


@app.post("/api/p/{pid}/notes")
def add_note(pid: str, req: NoteRequest):
    proj = get_project(pid)
    note = req.note.strip()
    if note:
        proj.notes.append(note)
        proj.save_notes()
        write_progress(proj)
        log.info(f"[{pid}] knowledge added by user: {_short(note, 90)}")
    return {"notes": proj.notes}


@app.put("/api/p/{pid}/notes/{index}")
def update_note(pid: str, index: int, req: NoteRequest):
    proj = get_project(pid)
    note = req.note.strip()
    if 0 <= index < len(proj.notes) and note:
        proj.notes[index] = note
        proj.save_notes()
        write_progress(proj)
        log.info(f"[{pid}] knowledge edited: {_short(note, 90)}")
    return {"notes": proj.notes}


@app.delete("/api/p/{pid}/notes/{index}")
def delete_note(pid: str, index: int):
    proj = get_project(pid)
    if 0 <= index < len(proj.notes):
        removed = proj.notes.pop(index)
        proj.save_notes()
        write_progress(proj)
        log.info(f"[{pid}] knowledge removed: {_short(removed, 90)}")
    return {"notes": proj.notes}


class ReorderRequest(BaseModel):
    order: list[int]


@app.post("/api/p/{pid}/dashboard/reorder")
def reorder_dashboard(pid: str, req: ReorderRequest):
    proj = get_project(pid)
    pos = {cid: i for i, cid in enumerate(req.order)}
    proj.dashboard.sort(key=lambda c: pos.get(c["id"], len(req.order)))
    proj.save_dash()
    log.info(f"[{pid}] dashboard reordered: {req.order}")
    return {"ok": True}


# ---------------------------------------------------------- data editor

def _validate_table(proj: Project, tname: str, lang: str = "bg") -> str:
    tables = [t["table"] for t in describe_schema(proj)]
    if tname not in tables:
        raise HTTPException(404, T(lang, "err_no_table", table=tname))
    return tname


@app.get("/api/p/{pid}/table/{tname}/rows")
def table_rows(pid: str, tname: str, request: Request, offset: int = 0, limit: int = 100,
               q: str = "", sort: str = "", dir: str = "asc"):
    proj = get_project(pid)
    _validate_table(proj, tname, req_lang(request))
    limit = max(1, min(limit, 200))
    cols = db.columns(pid, tname)
    colnames = [c[0] for c in cols]
    qi = lambda name: '"' + name.replace('"', '""') + '"'
    where, params = "", []
    if q.strip():
        text_cols = [c[0] for c in cols if "VARCHAR" in c[1].upper()] or colnames
        where = "WHERE (" + " OR ".join(f"CAST({qi(c)} AS TEXT) ILIKE %s" for c in text_cols) + ")"
        params = [f"%{q.strip()}%"] * len(text_cols)
    order = ""
    if sort in colnames:
        order = f'ORDER BY {qi(sort)} {"DESC" if dir == "desc" else "ASC"} NULLS LAST'
    total = int(db.query_df(pid, f"SELECT count(*) FROM {qi(tname)} {where}", params or None).iloc[0, 0])
    # ctid is the physical row address — stable enough for an inline edit right after listing
    df = db.query_df(pid, f"SELECT ctid::text AS __rid, * FROM {qi(tname)} {where} {order} "
                          f"LIMIT {limit} OFFSET {max(0, offset)}", params or None)
    return {"total": total, "offset": offset, "limit": limit,
            "columns": [{"name": c[0], "type": c[1]} for c in cols],
            "rows": frame_to_records(df)}


class CellEdit(BaseModel):
    rowid: str
    column: str
    value: str | None


@app.post("/api/p/{pid}/table/{tname}/cell")
def edit_cell(pid: str, tname: str, req: CellEdit, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    _validate_table(proj, tname, lang)
    cols = dict(db.columns(pid, tname))
    if True:
        if req.column not in cols:
            raise HTTPException(400, T(lang, "err_no_column", column=req.column))
        value = req.value
        ctype = cols[req.column].upper()
        if value is None or value == "":
            value = None
        elif any(t in ctype for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BIGINT")):
            try:
                value = float(str(value).replace(",", "."))
                if "INT" in ctype and float(value).is_integer():
                    value = int(value)
            except ValueError:
                raise HTTPException(400, T(lang, "err_not_number", value=req.value))
        if not re.fullmatch(r"\(\d+,\d+\)", req.rowid or ""):
            raise HTTPException(400, "bad row id")
        qi = lambda name: '"' + name.replace('"', '""') + '"'
        db.execute(pid, f"UPDATE {qi(tname)} SET {qi(req.column)} = %s WHERE ctid = %s::tid",
                   [value, req.rowid])
    log.info(f"[{pid}] edit: {tname}.{req.column} rowid={req.rowid} -> {_short(req.value, 60)}")
    proj.log_activity("info", T(lang, "act_edit", table=tname, column=req.column,
                                value=_short(req.value or '∅', 40)))
    return {"ok": True}


@app.post("/api/p/{pid}/dashboard/refresh")
def refresh_dashboard(pid: str, req: RefreshRequest, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    active = {k: v for k, v in req.selections.items() if v}
    log.info(f"[{pid}] refresh: filters {json.dumps(active, ensure_ascii=False)[:160]}")
    charts = []
    for c in proj.dashboard:
        chart = dict(c)
        try:
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, c["sql"], req.selections),
                                  MAX_CHART_ROWS)
            chart["rows"] = frame_to_records(df)
        except Exception as e:
            chart["error"] = str(e)
            log.info(f"[{pid}] refresh: chart #{c['id']} '{_short(c['title'], 40)}' ERROR — {_short(e, 120)}")
        charts.append(chart)
    i18n = {"needs_translation": False, "value_labels": {}, "field_labels": {}}
    filters = filters_with_options(proj)
    if lang != content_lang(proj):
        tr = _load_i18n(proj, lang)
        charts, i18n["field_labels"], i18n["value_labels"], pending = localize_charts(proj, lang, tr, charts)
        i18n["needs_translation"] = bool(pending)
        i18n["missing"] = len(pending)
        for f in filters:
            if _has_letters(f.get("label")):
                f["label"] = tr.get(_h(f["label"]), f["label"])
    return {"charts": charts, "filters": filters, "i18n": i18n}


@app.post("/api/p/{pid}/chat")
async def chat(pid: str, req: ChatRequest, request: Request):
    proj = get_project(pid)
    proj.lang = req_lang(request)
    proj.add_chat("user", req.message)
    return await dispatch_agent(proj, req.message)


@app.post("/api/p/{pid}/review")
async def review(pid: str, req: ReviewRequest, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    proj.add_chat("event", T(lang, "chat_files_loaded", tables=', '.join(req.tables)))
    upfront = ""
    if req.context.strip() or req.goal.strip():
        parts = []
        if req.context.strip():
            parts.append(T(lang, "chat_context", text=req.context.strip()))
        if req.goal.strip():
            parts.append(T(lang, "chat_goal", text=req.goal.strip()))
        user_text = "\n".join(parts)
        proj.add_chat("user", user_text)
        upfront = (f"\nThe user provided this upfront — treat it as answered "
                   f"interview ground truth, record every durable fact and goal "
                   f"with record_data_context, and do NOT re-ask about any of it:\n"
                   f"{user_text}\n")
    return await dispatch_agent(
        proj,
        f"[The user just uploaded file(s) loaded as: {', '.join(req.tables)}.{upfront}"
        "Follow your interview-mode instructions: investigate the new data, "
        "say briefly what you understood, and ask only the clarifying "
        "questions you really need (skip anything already answered above). "
        "Address the user directly.]"
    )


@app.post("/api/p/{pid}/reset")
async def reset(pid: str):
    proj = get_project(pid)
    if proj.sub_client is not None:
        try:
            await proj.sub_client.disconnect()
        except Exception:
            pass
        proj.sub_client = None
    proj.messages = []
    proj.dashboard = []
    proj.notes = []
    proj.filters = []
    proj.chat = []
    proj.chart_seq = 0
    proj.meta["files"] = {}
    proj.save_dash(); proj.save_notes(); proj.save_filters(); proj.save_chat(); proj.save_meta()
    if proj.progress_p.exists():
        proj.progress_p.unlink()
    proj.meta["views"] = {}
    proj.save_meta()
    try:
        db.drop_project(pid)
        db.ensure_project(pid)
    except Exception as e:
        log.info(f"[{pid}] reset: schema drop failed — {_short(e)}")
    shutil.rmtree(proj.uploads_dir, ignore_errors=True)
    proj.uploads_dir.mkdir(exist_ok=True)
    log.info(f"[{pid}] reset: all project state cleared")
    return {"ok": True}


# ------------------------------------------------------------ brand assets

BRAND_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".svg")


def brand_dir(proj: Project) -> Path:
    d = proj.dir / "brand"
    d.mkdir(exist_ok=True)
    return d


def brand_files(proj: Project) -> list:
    d = brand_dir(proj)
    return sorted(f.name for f in d.iterdir()
                  if f.suffix.lower() in BRAND_EXTS)


def brand_logo_path(proj: Project) -> Path | None:
    d = brand_dir(proj)
    imgs = [f for f in sorted(d.iterdir())
            if f.suffix.lower() in (".png", ".jpg", ".jpeg") and not f.name.startswith("_")]
    return imgs[0] if imgs else None


def brand_colors(proj: Project) -> list:
    p = brand_dir(proj) / "brand.json"
    try:
        return json.loads(p.read_text()).get("colors", []) if p.exists() else []
    except Exception:
        return []


def brand_theme(proj: Project) -> tuple:
    """(primary, accent) RGB from the brand book's hex codes; falls back to
    Inceptiq navy/cyan. Primary = darkest colour, accent = most vivid."""
    import colorsys
    p = brand_dir(proj) / "brand.json"
    primary, accent = NAVY_DEEP, CYAN
    try:
        if p.exists():
            hexes = json.loads(p.read_text()).get("colors", [])
            rgbs = [tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in hexes]
            rgbs = [r for r in rgbs if r != (1, 1, 1) and r != (0, 0, 0)]
            if rgbs:
                primary = min(rgbs, key=sum)

                def vivid(r):
                    h, l, s = colorsys.rgb_to_hls(*r)
                    return s * (1 - abs(l - 0.55))
                pool = [r for r in rgbs if r != primary] or rgbs
                accent = max(pool, key=vivid)
    except Exception:
        pass
    return primary, accent


def brand_excerpt(proj: Project, limit: int = 2500) -> str:
    """Concatenated text extracted from uploaded brand PDFs (for AI context)."""
    parts = []
    for f in sorted(brand_dir(proj).glob("*.txt")):
        try:
            parts.append(f"[{f.stem}]\n{f.read_text()[:limit]}")
        except Exception:
            continue
    return "\n\n".join(parts)[:limit]


def _prepare_logo(path: Path) -> Path:
    """Make an extracted logo usable: if it is a whole logo sheet, crop to the
    first (primary) logo on it; turn the white background transparent so the
    logo sits cleanly on dark covers. Saves as PNG."""
    try:
        import numpy as np
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        a = np.array(im)
        nonwhite = (a[..., :3] < 235).any(axis=2) & (a[..., 3] > 40)
        # density thresholds: thin caption lines between logos count as gaps
        rows = nonwhite.mean(axis=1) > 0.004
        if not rows.any():
            rows = nonwhite.any(axis=1)
        if not rows.any():
            return path
        ys = np.where(rows)[0]
        # first contiguous horizontal band of content (gap tolerance ~1.5% height)
        gap_y = max(10, im.height // 60)
        y0, y1 = int(ys[0]), int(ys[0])
        for y in ys:
            if y - y1 <= gap_y:
                y1 = int(y)
            else:
                break
        band = nonwhite[y0:y1 + 1]
        cols_d = band.mean(axis=0) > 0.004
        xs = np.where(cols_d)[0] if cols_d.any() else np.where(band.any(axis=0))[0]
        gap_x = max(14, im.width // 40)
        x0, x1 = int(xs[0]), int(xs[0])
        for x in xs:
            if x - x1 <= gap_x:
                x1 = int(x)
            else:
                break
        # degenerate crop -> fall back to the bbox of everything
        if (x1 - x0) < im.width * 0.1 or (y1 - y0) < 16:
            xs_all = np.where(nonwhite.any(axis=0))[0]
            x0, x1, y0, y1 = int(xs_all[0]), int(xs_all[-1]), int(ys[0]), int(ys[-1])
        pad = 16
        crop = im.crop((max(0, x0 - pad), max(0, y0 - pad),
                        min(im.width, x1 + pad), min(im.height, y1 + pad)))
        arr = np.array(crop)
        arr[(arr[..., :3] > 242).all(axis=2), 3] = 0   # white -> transparent
        out = path.parent / (path.stem + ".png")
        Image.fromarray(arr).save(out)
        if out != path and path.exists():
            path.unlink()
        return out
    except Exception as e:
        log.info(f"logo prepare failed — {_short(e)}")
        return path


def extract_brand_assets(proj: Project):
    """Text, colours and a usable logo out of the uploaded brand files.
    Idempotent — runs on upload and as a backfill for older uploads."""
    import re as _re
    import subprocess
    d = brand_dir(proj)
    pdfs = sorted(d.glob("*.pdf"))

    # 1) text from every brand PDF
    for f in pdfs:
        txt = d / (f.stem + ".txt")
        if txt.exists():
            continue
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(f))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:8])
            txt.write_text(text.strip()[:20000])
        except Exception as e:
            log.info(f"[{proj.id}] brand: text extract failed for '{f.name}' — {_short(e)}")

    # 2) colours: hex codes and "R: 2 G: 59 B: 89" style breakdowns
    hexes: list = []
    for txt in sorted(d.glob("*.txt")):
        try:
            t = txt.read_text()
        except Exception:
            continue
        hexes += [h.upper() for h in _re.findall(r"#[0-9a-fA-F]{6}", t)]
        for r, g, b in _re.findall(
                r"R:?\s*(\d{1,3})[,;\s]+G:?\s*(\d{1,3})[,;\s]+B:?\s*(\d{1,3})", t):
            if all(int(v) <= 255 for v in (r, g, b)):
                hexes.append("#%02X%02X%02X" % (int(r), int(g), int(b)))
    hexes = list(dict.fromkeys(hexes))[:12]

    # fonts: scan the book text against known typeface names, in order of
    # first appearance (first mention is usually the primary typeface)
    KNOWN_FONTS = [
        "IBM Plex Sans", "IBM Plex Serif", "Helvetica Neue", "Helvetica",
        "Roboto Condensed", "Roboto Slab", "Roboto", "Inter", "Montserrat",
        "Open Sans", "Source Sans", "Noto Sans", "Lato", "Poppins", "Raleway",
        "Work Sans", "DM Sans", "PT Sans", "Nunito Sans", "Nunito", "Manrope",
        "Rubik", "Ubuntu", "Mulish", "Barlow", "Karla", "Georgia", "Garamond",
        "Playfair Display", "Merriweather", "Arial", "Verdana", "Futura",
        "Gotham", "Proxima Nova", "Avenir",
    ]
    all_text = "\n".join(t.read_text() for t in sorted(d.glob("*.txt")) if t.exists())
    found, names = [], []
    low = all_text.lower()
    for fam in KNOWN_FONTS:
        m = _re.search(r"\b" + _re.escape(fam.lower()) + r"\b", low)
        if m and not any(fam in n for n in names):
            found.append((m.start(), fam))
            names.append(fam)
    fonts = [fam for _, fam in sorted(found)][:3]

    if hexes or fonts:
        had = (d / "brand.json").exists()
        (d / "brand.json").write_text(json.dumps({"colors": hexes, "fonts": fonts}))
        log.info(f"[{proj.id}] brand: colours: {hexes} | fonts: {fonts}")
        if not had:
            proj.log_activity("info", T(proj.lang, "act_brand_extracted",
                                        colors=len(hexes), fonts=len(fonts)))

    # Logos are NEVER auto-extracted from the book — the logo is whatever
    # image the user uploads explicitly. The book contributes colours only.


@app.post("/api/p/{pid}/brand")
async def brand_upload(pid: str, request: Request, files: list[UploadFile] = File(...)):
    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    d = brand_dir(proj)
    saved = []
    for f in files:
        fname = Path(f.filename).name
        if Path(fname).suffix.lower() not in BRAND_EXTS:
            raise HTTPException(400, T(lang, "err_brand_ext", name=fname))
        payload = await f.read()
        (d / fname).write_bytes(payload)
        saved.append(fname)
        log.info(f"[{pid}] brand: uploaded '{fname}' ({len(payload) // 1024} KB)")
        proj.log_activity("info", T(lang, "act_brand_file", name=fname))
    # a new PDF replaces previously auto-extracted assets (explicit images stay)
    if any(s.lower().endswith(".pdf") for s in saved):
        for stale in brand_dir(proj).glob("_logo_from_book.*"):
            stale.unlink()
        for s in saved:   # re-extract text of re-uploaded books
            if s.lower().endswith(".pdf"):
                stale_txt = brand_dir(proj) / (Path(s).stem + ".txt")
                if stale_txt.exists():
                    stale_txt.unlink()
    extract_brand_assets(proj)
    return {"brand": brand_files(proj), "saved": saved}


@app.get("/api/p/{pid}/brand/file/{filename}")
def brand_file(pid: str, filename: str, request: Request):
    proj = get_project(pid)
    f = brand_dir(proj) / Path(filename).name
    if not f.exists():
        raise HTTPException(404, T(req_lang(request), "err_brand_missing"))
    return FileResponse(f)


@app.delete("/api/p/{pid}/brand/{filename}")
def brand_delete(pid: str, filename: str):
    proj = get_project(pid)
    fname = Path(filename).name
    d = brand_dir(proj)
    for p in [d / fname, d / (Path(fname).stem + ".txt")]:
        if p.exists():
            p.unlink()
    log.info(f"[{pid}] brand: deleted '{fname}'")
    return {"brand": brand_files(proj)}


# ------------------------------------------------------- presentation deck

DECK_PROMPT = """[Task: write the content of a presentation about the current
dashboard, the way an experienced business analyst would write it for a live
audience.

Language: write ALL titles, headlines, narratives, agenda items, section
headings and takeaways in __LANGUAGE__ (the UI language). Keep data values as
they appear in the data.

Style (important):
- Every slide title is the MESSAGE with the number, not a description of the
  chart ("Growth comes entirely from the wholesale channel: 50% share vs 27% a
  year ago", not "Chart of channels").
- Under every title: 2-3 short human sentences that tell what is visible, why
  it happened and what follows from it. Write like a person: no long dashes, no
  bureaucratic language, no bullet lists inside the narrative.
- Group the slides into 2-4 logical sections with clear headings that together
  tell a story (big picture -> details -> people/products -> conclusions).
- Every dashboard chart is used EXACTLY once.
- Final slide "Key takeaways and recommendations": 3-5 concrete recommendations
  with numbers.

Use the project knowledge and the numbers from the charts. If you need a
specific figure, verify it with run_sql_query.

Finally, also write a BRIEF for the design tool (Gamma) that will lay out the
slides. Derive it from the project knowledge (who the client is, what the goal
of the analysis is, who it is for), from the brand book (if present — the tone
of the brand) and from the charts we have:
- "audience": who the presentation is for (short, concrete).
- "tone": how it should sound (2-5 words).
- "emphasis": 2-4 things that must stand out (with numbers).
- "instructions": the brief itself IN ENGLISH (always English, whatever the UI
  language), 3-6 sentences, for Gamma: audience, tone, what to emphasise, how
  to order (e.g. summary first, next steps last), never change the numbers and
  keep the charts large and unmodified.
- "text_mode": "preserve" if your narratives are complete enough, "generate" if
  you want Gamma to expand them, "condense" if they are long.
- "image_source": "noImages" for a strict report (only our charts),
  "themeAccent" for a more visual presentation for a broad audience.
- "num_cards": recommended number of slides (sections + slides + cover + takeaways).

Return ONLY valid JSON (no markdown, no comments) in this format:
{"title": "...", "subtitle": "...",
 "agenda": ["...", "..."],
 "sections": [{"heading": "...",
               "slides": [{"chart_id": 1, "headline": "...", "narrative": "..."}]}],
 "takeaways": [{"title": "...", "text": "..."}],
 "gamma": {"audience": "...", "tone": "...", "emphasis": ["...", "..."],
           "instructions": "...", "text_mode": "preserve", "image_source": "noImages",
           "num_cards": 10}}

Brand book (excerpt): __BRAND__

Dashboard charts:
__CHARTS__]"""


@app.post("/api/p/{pid}/deck")
async def make_deck(pid: str, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    if not proj.dashboard:
        raise HTTPException(400, T(lang, "err_deck_no_charts"))
    charts_brief = [{"id": c["id"], "title": c["title"], "type": c["chart_type"],
                     "insight": c["insight"], "sample_rows": c["rows"][:3]}
                    for c in proj.dashboard]
    t0 = time.monotonic()
    log.info(f"[{pid}] deck: writing presentation content…")
    proj.log_activity("info", T(lang, "act_deck_writing"))
    prompt = (DECK_PROMPT
              .replace("__LANGUAGE__", LANG_NAMES[lang])
              .replace("__BRAND__", brand_excerpt(proj, 1500) or T(lang, "deck_no_brand"))
              .replace("__CHARTS__", json.dumps(charts_brief, ensure_ascii=False, default=str)))
    result = (await run_agent_subscription(proj, prompt)
              if AI_BACKEND == "subscription"
              else await run_in_threadpool(run_agent_api, proj, prompt))
    raw = result["reply"].strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise HTTPException(502, T(lang, "err_deck_invalid"))
    try:
        spec = json.loads(m.group(0))
    except Exception:
        raise HTTPException(502, T(lang, "err_deck_json"))
    log.info(f"[{pid}] deck: done in {time.monotonic() - t0:.1f}s — "
             f"{sum(len(s.get('slides', [])) for s in spec.get('sections', []))} слайда, "
             f"{len(spec.get('sections', []))} секции")
    g = spec.get("gamma") or {}
    if g.get("audience"):
        log.info(f"[{pid}] deck: brief — аудитория: {_short(g.get('audience'), 80)} | тон: {_short(g.get('tone'), 60)}")
    proj.add_chat("ai", T(lang, "chat_deck_ready"))
    return {"spec": spec}


# ------------------------------------------------------------- PDF export

NAVY = (8 / 255, 32 / 255, 66 / 255)
NAVY_DEEP = (4 / 255, 20 / 255, 44 / 255)
CYAN = (10 / 255, 221 / 255, 245 / 255)


def _register_pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "Brand" in pdfmetrics.getRegisteredFontNames():
        return
    reg = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    pdfmetrics.registerFont(TTFont("Brand", reg))
    pdfmetrics.registerFont(TTFont("Brand-Bold", bold if Path(bold).exists() else reg))


class ExportChart(BaseModel):
    title: str
    insight: str = ""
    chart_type: str
    image: str | None = None          # dataURL PNG for chart types
    columns: list[str] | None = None  # for table charts
    rows: list[list] | None = None


class ExportRequest(BaseModel):
    charts: list[ExportChart]
    filters_line: str = ""


@app.post("/api/p/{pid}/export/pdf")
def export_pdf(pid: str, req: ExportRequest, request: Request):
    import base64
    import io as _io

    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors as rl

    proj = get_project(pid)
    lang = req_lang(request)
    proj.lang = lang
    _register_pdf_fonts()
    PRIMARY, ACCENT = brand_theme(proj)
    W, H = landscape(A4)
    M = 40                               # page margin
    buf = _io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(W, H))
    today = time.strftime(T(lang, "date_fmt"))

    def wrap(text, font, size, maxw, max_lines):
        words, line, lines = text.split(), "", []
        for w_ in words:
            t = (line + " " + w_).strip()
            if c.stringWidth(t, font, size) <= maxw:
                line = t
            else:
                lines.append(line)
                line = w_
                if len(lines) == max_lines:
                    return lines
        if line:
            lines.append(line)
        return lines[:max_lines]

    def page_chrome(page_no):
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setFillColorRGB(*ACCENT)
        c.rect(0, H - 5, W, 5, stroke=0, fill=1)
        c.setFillColorRGB(*PRIMARY)
        c.setFont("Brand-Bold", 10)
        c.drawString(M, H - 26, proj.meta["name"])
        c.setFont("Brand", 8)
        c.setFillColorRGB(0.55, 0.58, 0.62)
        c.drawRightString(W - M, H - 26, f"{T(lang, 'pdf_report')} · {today}")
        c.drawRightString(W - M, 18, T(lang, "pdf_page", n=page_no))

    def draw_chart_cell(ch, x0, y0, cw, chh):
        c.setFillColorRGB(*PRIMARY)
        c.setFont("Brand-Bold", 12)
        c.drawString(x0, y0 + chh - 14, _short(ch.title, int(cw / 6)))
        ty = y0 + chh - 30
        if ch.insight:
            c.setFillColorRGB(0.35, 0.39, 0.45)
            c.setFont("Brand", 8.5)
            for ln in wrap(ch.insight, "Brand", 8.5, cw, 2):
                c.drawString(x0, ty, ln)
                ty -= 11
        img_top = ty - 4
        img_h = img_top - y0
        if ch.image:
            try:
                raw = base64.b64decode(ch.image.split(",", 1)[1])
                img = ImageReader(_io.BytesIO(raw))
                iw, ih = img.getSize()
                scale = min(cw / iw, img_h / ih)
                dw, dh = iw * scale, ih * scale
                c.drawImage(img, x0 + (cw - dw) / 2, img_top - dh, dw, dh, mask="auto")
            except Exception as e:
                log.info(f"[{pid}] export: image failed — {_short(e)}")

    # ---- title page (white, so the brand logo shows in its own colours)
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColorRGB(*ACCENT)
    c.rect(0, H - 8, W, 8, stroke=0, fill=1)
    c.setFillColorRGB(*PRIMARY)
    c.rect(0, 0, W, 3, stroke=0, fill=1)
    logo = brand_logo_path(proj)
    y_center = H / 2 + 30
    if logo:
        try:
            img = ImageReader(str(logo))
            iw, ih = img.getSize()
            lw = min(230, W * 0.28)
            lh = lw * ih / iw
            if lh > 130:
                lh, lw = 130, 130 * iw / ih
            c.drawImage(img, (W - lw) / 2, y_center + 36, lw, lh,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    c.setFillColorRGB(*PRIMARY)
    c.setFont("Brand-Bold", 32)
    c.drawCentredString(W / 2, y_center - 16, proj.meta["name"])
    c.setFont("Brand", 15)
    c.setFillColorRGB(*ACCENT)
    c.drawCentredString(W / 2, y_center - 50, T(lang, "pdf_report"))
    c.setFillColorRGB(0.45, 0.49, 0.54)
    c.setFont("Brand", 11)
    c.drawCentredString(W / 2, y_center - 78, today)
    if req.filters_line:
        c.drawCentredString(W / 2, y_center - 98, T(lang, "pdf_filters", text=_short(req.filters_line, 110)))
    c.showPage()

    # ---- content: tables get a full page; charts go two per page
    page = 2
    tables = [ch for ch in req.charts if ch.columns is not None]
    charts = [ch for ch in req.charts if ch.image]

    for ch in tables:
        page_chrome(page)
        c.setFillColorRGB(*PRIMARY)
        c.setFont("Brand-Bold", 15)
        c.drawString(M, H - 58, _short(ch.title, 90))
        top = H - 74
        if ch.insight:
            c.setFillColorRGB(0.35, 0.39, 0.45)
            c.setFont("Brand", 9.5)
            for ln in wrap(ch.insight, "Brand", 9.5, W - 2 * M, 2):
                c.drawString(M, top, ln)
                top -= 13
            top -= 4
        data = [ch.columns] + [[("" if v is None else str(v)) for v in r]
                               for r in (ch.rows or [])[:15]]
        col_w = (W - 2 * M) / max(1, len(ch.columns))
        tbl = Table(data, colWidths=[col_w] * len(ch.columns))
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Brand"),
            ("FONTNAME", (0, 0), (-1, 0), "Brand-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl.white),
            ("BACKGROUND", (0, 0), (-1, 0), rl.Color(*PRIMARY)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl.white, rl.Color(0.958, 0.966, 0.974)]),
            ("TEXTCOLOR", (0, 1), (-1, -1), rl.Color(0.2, 0.24, 0.3)),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, rl.Color(*ACCENT)),
            ("GRID", (0, 0), (-1, -1), 0.3, rl.Color(0.87, 0.89, 0.92)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        tw, th = tbl.wrapOn(c, W - 2 * M, top - 40)
        tbl.drawOn(c, M, max(34, top - th))
        c.showPage()
        page += 1

    cw = (W - 2 * M - 28) / 2
    chh = H - 110
    for i in range(0, len(charts), 2):
        page_chrome(page)
        draw_chart_cell(charts[i], M, 40, cw, chh)
        if i + 1 < len(charts):
            c.setStrokeColorRGB(0.9, 0.91, 0.93)
            c.setLineWidth(0.6)
            c.line(W / 2, 46, W / 2, H - 52)
            draw_chart_cell(charts[i + 1], M + cw + 28, 40, cw, chh)
        c.showPage()
        page += 1

    c.save()
    pdf = buf.getvalue()
    log.info(f"[{pid}] export: PDF generated — {len(req.charts)} страници графики, {len(pdf) // 1024} KB")
    proj.log_activity("info", T(lang, "act_pdf", n=len(req.charts)))
    fname = f"{proj.id}-report.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ------------------------------------------------------------------- pages

NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


@app.get("/")
def landing():
    return FileResponse(ROOT / "static" / "landing.html", headers=NO_CACHE)


@app.get("/app")
def app_page():
    return FileResponse(ROOT / "static" / "app.html", headers=NO_CACHE)



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
                 "User-Agent": "InceptiqAnalytics/1.0 (+https://inceptiq.ai)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        log.info(f"gamma: {method} {path} -> {e.code} {detail}")
        raise HTTPException(502, T(lang, "err_gamma_status", code=e.code, detail=detail))
    except Exception as e:
        raise HTTPException(502, T(lang, "err_gamma_unreachable", detail=_short(e)))


@app.get("/api/gamma/options")
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
        "public_images": bool(PUBLIC_BASE_URL),
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


@app.post("/api/p/{pid}/gamma")
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


@app.get("/api/gamma/status/{gid}")
def gamma_status(gid: str):
    d = _gamma_call("GET", f"/generations/{gid}")
    if d.get("status") in ("completed", "failed"):
        log.info(f"gamma: {gid} -> {d.get('status')} {d.get('gammaUrl', '')}")
    return {"status": d.get("status"), "gamma_url": d.get("gammaUrl"),
            "export_url": d.get("exportUrl"), "credits": d.get("credits"),
            "error": d.get("error")}


@app.get("/pub/{token}/{name}")
def pub_file(token: str, name: str):
    """Unauthenticated assets for Gamma's fetchers (unguessable token path)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", token) or "/" in name or name.startswith("."):
        raise HTTPException(404)
    f = PUB_DIR / token / name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
