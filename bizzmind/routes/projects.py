"""Project routes: list/create/delete, state, activity, jobs API, upload, notes,
data editor, dashboard refresh, translate, chat, review, deck, reset."""

import asyncio
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

import db
import jobs
import storage
import auth as sb_auth
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from bizzmind.config import INLINE_JOBS, MAX_CHART_ROWS, PROJECTS_DIR, _short, log
from bizzmind.i18n import MSG, T, req_lang
from bizzmind.project import PROJECTS, Project, get_project, require_project_access, write_progress
from bizzmind.data import (invalidate, apply_filters_to_sql, describe_schema, filters_with_options,
                           frame_to_records, load_frames_from_upload, run_readonly_sql,
                           verify_dashboard)
from bizzmind.brand import brand_colors, brand_dir, brand_files, brand_logo_path, brand_theme
from bizzmind.localization import (_h, _has_letters, _load_i18n, content_lang, localize_charts,
                                   localized_content, translatable_items)
from bizzmind.agent import dispatch_agent, run_deck, run_review, run_translate

router = APIRouter()


@router.get("/api/jobs/{job_id}")
def job_status(job_id: str, since: int = 0):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    get_project(j["project_id"])            # tenancy check
    return {"id": j["id"], "kind": j["kind"], "status": j["status"], "error": j["error"],
            "result": j["result"] if j["status"] == "done" else None,
            "events": jobs.events(job_id, since)}


async def _execute_claimed(job: dict) -> dict:
    """Run a claimed job in-process (same code path as worker.py)."""
    import time as _time
    from bizzmind.agent import dispatch_agent, run_review, run_deck, run_translate
    from bizzmind.project import PROJECTS
    t0 = _time.monotonic()
    proj = get_project(job["project_id"])
    proj.lang = job.get("lang") or "bg"
    proj.job_id = job["id"]
    kind, pl = job["kind"], job["payload"] or {}
    try:
        if kind == "chat":
            proj.add_chat("user", pl["message"])
            result = await dispatch_agent(proj, pl["message"])
        elif kind == "review":
            result = await run_review(proj, pl.get("tables") or [], pl.get("context", ""), pl.get("goal", ""))
        elif kind == "deck":
            result = await run_deck(proj)
        elif kind == "translate":
            result = await run_translate(proj)
        else:
            raise ValueError(f"unknown job kind '{kind}'")
        jobs.finish(job["id"], result)
        log.info(f"[{proj.id}] job {job['id']} done inline in {_time.monotonic() - t0:.1f}s")
        return {"status": "done"}
    except Exception as e:
        jobs.fail(job["id"], str(e))
        log.info(f"[{proj.id}] job {job['id']} FAILED inline — {_short(e, 200)}")
        return {"status": "failed", "error": str(e)}
    finally:
        proj.job_id = None
        PROJECTS.pop(proj.id, None)


@router.post("/api/jobs/{job_id}/run")
async def run_job_now(job_id: str):
    """Serverless worker: the client calls this right after enqueue; the request
    stays open while the job runs (Vercel maxDuration). A separate worker
    process, if any, may already have claimed it — then this is a no-op."""
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    get_project(j["project_id"])            # tenancy check
    job = jobs.claim_by_id(job_id)
    if not job:
        return {"status": j["status"], "claimed": False}
    return await _execute_claimed(job)


@router.api_route("/api/cron/jobs", methods=["GET", "POST"])
async def jobs_cron(request: Request):
    """Vercel Cron fallback: re-queue stale jobs and run up to 3 queued ones."""
    secret = os.environ.get("CRON_SECRET")
    if secret and request.headers.get("authorization") != f"Bearer {secret}":
        raise HTTPException(401, "unauthorized")
    requeued = jobs.requeue_stale()
    done = 0
    for _ in range(3):
        job = jobs.claim()
        if not job:
            break
        await _execute_claimed(job)
        done += 1
    return {"requeued": requeued, "ran": done}


@router.get("/api/p/{pid}/jobs/active")
def active_job(pid: str):
    get_project(pid)
    j = jobs.latest_for_project(pid)
    return {"job": {"id": j["id"], "kind": j["kind"], "status": j["status"]} if j else None}


# ------------------------------------------------------------ project routes

class ProjectCreate(BaseModel):
    name: str


@router.get("/api/projects")
def list_projects():
    # one-time lift of pre-Supabase projects (folders with meta.json but no DB row)
    legacy = [d for d in PROJECTS_DIR.iterdir() if d.is_dir() and (d / "meta.json").exists()] if PROJECTS_DIR.exists() else []
    if legacy:
        known = {r["id"] for r in db.project_list()}
        for pdir in legacy:
            if pdir.name not in known:
                try:
                    get_project(pdir.name)
                except Exception as e:
                    log.info(f"[{pdir.name}] legacy import failed — {_short(e)}")
        for pdir in legacy:   # imported -> retire the marker so this scan stays a no-op
            try:
                (pdir / "meta.json").rename(pdir / "meta.legacy.json")
            except Exception:
                pass
    u = sb_auth.current_user()
    out = [{"id": r["id"], "name": r["name"], "created": r["created"], "tables": r["tables"],
            "charts": r["charts"], "notes": r["notes"]}
           for r in db.project_list() if u is None or u.can_read(r.get("org_id"))]
    return {"projects": out}


@router.post("/api/projects")
def create_project(req: ProjectCreate, request: Request):
    name = req.name.strip() or T(req_lang(request), "new_project")
    # project ids are ASCII URL slugs; non-Latin names fall back to a random id
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or f"project-{uuid.uuid4().hex[:6]}"
    pid = slug if not (db.project_exists(slug) or (PROJECTS_DIR / slug).exists()) else f"{slug}-{uuid.uuid4().hex[:6]}"
    (PROJECTS_DIR / pid).mkdir(parents=True, exist_ok=True)
    db.ensure_project(pid)
    u = sb_auth.current_user()
    org = (u.orgs[0] if u and u.orgs else db.default_org())
    db.project_create(pid, name, org_id=org,
                      meta={"name": name, "created": time.strftime("%Y-%m-%d"), "files": {}})
    proj = get_project(pid)
    write_progress(proj)
    log.info(f"[{pid}] project created: '{name}'")
    return {"id": pid, "name": name}


@router.put("/api/projects/{pid}")
def rename_project(pid: str, req: ProjectCreate):
    proj = get_project(pid)
    name = req.name.strip()
    if name:
        proj.meta["name"] = name
        proj.save_meta()
        log.info(f"[{pid}] project renamed to '{name}'")
    return {"id": pid, "name": proj.meta["name"]}


@router.delete("/api/projects/{pid}")
async def delete_project(pid: str):
    proj = get_project(pid)
    require_project_access(proj, admin=True)
    if proj.sub_client is not None:
        try:
            await proj.sub_client.disconnect()
        except Exception:
            pass
    PROJECTS.pop(pid, None)
    shutil.rmtree(proj.dir, ignore_errors=True)
    try:
        storage.delete_prefix(pid)
    except Exception as e:
        log.info(f"[{pid}] storage cleanup failed — {_short(e)}")
    try:
        db.project_delete(pid)
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


@router.get("/api/p/{pid}/verify")
def verify_endpoint(pid: str):
    return verify_dashboard(get_project(pid))


class RefreshRequest(BaseModel):
    selections: dict


class NoteRequest(BaseModel):
    note: str


@router.post("/api/p/{pid}/translate")
async def translate_content(pid: str, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    if INLINE_JOBS:
        proj.lang = lang
        return await run_translate(proj)
    src = content_lang(proj)
    if lang == src or not [k for k in translatable_items(proj, lang) if k not in _load_i18n(proj, lang)]:
        return {"translated": 0, "content_lang": src, "reply": None}
    u = sb_auth.current_user()
    return {"job_id": jobs.enqueue(pid, "translate", {}, lang, u.id if u else None)}


@router.get("/api/p/{pid}/state")
def state(pid: str, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    # remote Postgres: run the independent pieces side by side (schema, filters/options)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_schema = ex.submit(describe_schema, proj)
        f_content = ex.submit(localized_content, proj, lang)
        tables = f_schema.result()
        charts, notes, filters, i18n = f_content.result()
    return {"name": proj.meta.get("name", pid),
            "tables": tables, "charts": charts,
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


@router.get("/api/p/{pid}/activity")
def activity(pid: str, since: int = 0):
    proj = get_project(pid)
    return {"events": [e for e in proj.activity if e["seq"] > since], "seq": proj.act_seq}


async def _ingest(proj, fname: str, payload: bytes, loaded: list) -> None:
    """Parse one spreadsheet into the project's tables (shared by both upload paths)."""
    pid = proj.id
    log.info(f"[{pid}] upload: parsing '{fname}' ({len(payload) // 1024} KB)")
    (proj.uploads_dir / fname).write_bytes(payload)
    file_tables = []
    for table, df in load_frames_from_upload(fname, payload).items():
        await run_in_threadpool(db.load_frame, pid, table, df)
        invalidate(pid)
        loaded.append({"table": table, "rows": len(df)})
        file_tables.append(table)
        log.info(f"[{pid}] upload: table '{table}' loaded — {len(df)} rows, "
                 f"{len(df.columns)} cols: {_short(', '.join(map(str, df.columns)), 110)}")
        proj.log_activity("info", T(proj.lang, "act_table_loaded", table=table,
                                    rows=len(df), cols=len(df.columns)))
    proj.meta["files"][fname] = file_tables


@router.post("/api/p/{pid}/upload")
async def upload(pid: str, request: Request, files: list[UploadFile] = File(...)):
    """Direct multipart upload (small files / local dev). Hosted API bodies are
    capped (~4.5 MB on Vercel) — the web app uses /upload/sign + /upload/ingest."""
    proj = get_project(pid)
    proj.lang = req_lang(request)
    log.info(f"[{pid}] upload: {len(files)} file(s) received")
    proj.ensure_uploads()
    loaded = []
    db.ensure_project(pid)
    try:
        for f in files:
            await _ingest(proj, Path(f.filename).name, await f.read(), loaded)
    finally:
        proj.save_meta()
        await run_in_threadpool(storage.sync_up, pid, "uploads", proj.uploads_dir)
    log.info(f"[{pid}] upload: done — {len(loaded)} table(s), {sum(l['rows'] for l in loaded)} rows total")
    write_progress(proj)
    return {"loaded": loaded, "tables": describe_schema(proj)}


class SignRequest(BaseModel):
    filenames: list[str]


@router.post("/api/p/{pid}/upload/sign")
def upload_sign(pid: str, req: SignRequest, request: Request):
    """Signed Storage URLs: the browser PUTs the files straight to Supabase."""
    proj = get_project(pid)
    if not storage.enabled():
        raise HTTPException(503, "storage not configured")
    out = []
    for name in req.filenames[:20]:
        fname = Path(name).name
        if Path(fname).suffix.lower() not in (".xlsx", ".xls", ".csv"):
            raise HTTPException(400, T(req_lang(request), "err_upload_type", name=fname) if "err_upload_type" in MSG["bg"] else f"Unsupported file type: {fname}")
        out.append({"filename": fname, "url": storage.signed_upload_url(f"{proj.id}/uploads/{fname}")})
    return {"files": out}


@router.post("/api/p/{pid}/upload/ingest")
async def upload_ingest(pid: str, req: SignRequest, request: Request):
    """After the browser uploaded to Storage: pull the files and load them."""
    proj = get_project(pid)
    proj.lang = req_lang(request)
    loaded = []
    db.ensure_project(pid)
    try:
        for name in req.filenames[:20]:
            fname = Path(name).name
            payload = await run_in_threadpool(storage.get, f"{pid}/uploads/{fname}")
            await _ingest(proj, fname, payload, loaded)
    finally:
        proj.save_meta()
    log.info(f"[{pid}] upload(storage): done — {len(loaded)} table(s), {sum(l['rows'] for l in loaded)} rows total")
    write_progress(proj)
    return {"loaded": loaded, "tables": describe_schema(proj)}


@router.delete("/api/p/{pid}/files/{filename}")
def delete_file(pid: str, filename: str):
    proj = get_project(pid)
    proj.ensure_uploads()
    fname = Path(filename).name
    tables = proj.meta["files"].pop(fname, [])
    for t in tables:
        try:
            db.drop_table(pid, t)
            invalidate(pid)
        except Exception as e:
            log.info(f"[{pid}] drop table '{t}' failed — {_short(e)}")
    upload_file = proj.uploads_dir / fname
    if upload_file.exists():
        upload_file.unlink()
    storage.sync_up(pid, "uploads", proj.uploads_dir)
    proj.save_meta()
    write_progress(proj)
    log.info(f"[{pid}] file deleted: '{fname}' (+{len(tables)} table(s))")
    return {"ok": True, "dropped_tables": tables}


@router.post("/api/p/{pid}/notes")
def add_note(pid: str, req: NoteRequest):
    proj = get_project(pid)
    note = req.note.strip()
    if note:
        proj.notes.append(note)
        proj.save_notes()
        write_progress(proj)
        log.info(f"[{pid}] knowledge added by user: {_short(note, 90)}")
    return {"notes": proj.notes}


@router.put("/api/p/{pid}/notes/{index}")
def update_note(pid: str, index: int, req: NoteRequest):
    proj = get_project(pid)
    note = req.note.strip()
    if 0 <= index < len(proj.notes) and note:
        proj.notes[index] = note
        proj.save_notes()
        write_progress(proj)
        log.info(f"[{pid}] knowledge edited: {_short(note, 90)}")
    return {"notes": proj.notes}


@router.delete("/api/p/{pid}/notes/{index}")
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


@router.post("/api/p/{pid}/dashboard/reorder")
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


@router.get("/api/p/{pid}/table/{tname}/rows")
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


@router.post("/api/p/{pid}/table/{tname}/cell")
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
        invalidate(pid)
        db.execute(pid, f"UPDATE {qi(tname)} SET {qi(req.column)} = %s WHERE ctid = %s::tid",
                   [value, req.rowid])
    log.info(f"[{pid}] edit: {tname}.{req.column} rowid={req.rowid} -> {_short(req.value, 60)}")
    proj.log_activity("info", T(lang, "act_edit", table=tname, column=req.column,
                                value=_short(req.value or '∅', 40)))
    return {"ok": True}


@router.post("/api/p/{pid}/dashboard/refresh")
async def refresh_dashboard(pid: str, req: RefreshRequest, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    active = {k: v for k, v in req.selections.items() if v}
    log.info(f"[{pid}] refresh: filters {json.dumps(active, ensure_ascii=False)[:160]}")

    def run_one(c):
        chart = dict(c)
        try:
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, c["sql"], req.selections), MAX_CHART_ROWS)
            chart["rows"] = frame_to_records(df)
        except Exception as e:
            chart["error"] = str(e)
            log.info(f"[{pid}] refresh: chart #{c['id']} '{_short(c['title'], 40)}' ERROR — {_short(e, 120)}")
        return chart
    # every chart is one remote round trip -> run them concurrently
    charts = list(await asyncio.gather(*[run_in_threadpool(run_one, c) for c in proj.dashboard]))
    i18n = {"needs_translation": False, "value_labels": {}, "field_labels": {}}
    filters = filters_with_options(proj)
    if lang != content_lang(proj):
        tr = _load_i18n(proj, lang)
        charts, i18n["field_labels"], i18n["value_labels"], _ = localize_charts(proj, lang, tr, charts)
        for f in filters:
            if _has_letters(f.get("label")):
                f["label"] = tr.get(_h(f["label"]), f["label"])
    return {"charts": charts, "filters": filters, "i18n": i18n}


@router.post("/api/p/{pid}/chat")
async def chat(pid: str, req: ChatRequest, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    if INLINE_JOBS:
        proj.lang = lang
        proj.add_chat("user", req.message)
        return await dispatch_agent(proj, req.message)
    u = sb_auth.current_user()
    return {"job_id": jobs.enqueue(pid, "chat", {"message": req.message}, lang, u.id if u else None)}


@router.post("/api/p/{pid}/review")
async def review(pid: str, req: ReviewRequest, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    if INLINE_JOBS:
        proj.lang = lang
        return await run_review(proj, req.tables, req.context, req.goal)
    u = sb_auth.current_user()
    return {"job_id": jobs.enqueue(pid, "review", {"tables": req.tables, "context": req.context,
                                                    "goal": req.goal}, lang, u.id if u else None)}


@router.post("/api/p/{pid}/reset")
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
    proj.i18n = {}
    proj.save_i18n()
    db.project_save(pid, progress=None)
    proj.meta["views"] = {}
    proj.save_meta()
    try:
        db.drop_project(pid)
        db.ensure_project(pid)
    except Exception as e:
        log.info(f"[{pid}] reset: schema drop failed — {_short(e)}")
    shutil.rmtree(proj.uploads_dir, ignore_errors=True)
    proj.uploads_dir.mkdir(exist_ok=True)
    storage.sync_up(pid, "uploads", proj.uploads_dir)
    invalidate(pid)
    log.info(f"[{pid}] reset: all project state cleared")
    return {"ok": True}


@router.post("/api/p/{pid}/deck")
async def make_deck(pid: str, request: Request):
    proj = get_project(pid)
    lang = req_lang(request)
    if not proj.dashboard:
        raise HTTPException(400, T(lang, "err_deck_no_charts"))
    if INLINE_JOBS:
        proj.lang = lang
        return await run_deck(proj)
    u = sb_auth.current_user()
    return {"job_id": jobs.enqueue(pid, "deck", {}, lang, u.id if u else None)}
