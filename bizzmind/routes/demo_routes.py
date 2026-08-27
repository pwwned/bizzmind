"""Public demo: one fixed, synthetic project served read-only without login.

Nothing here touches AI (so traffic costs nothing) and nothing here can reach
another project: the id is hard-coded and every route is read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from bizzmind.config import DATA_DIR, log
from bizzmind.data import (apply_filters_to_sql, describe_schema, filters_with_options,
                           frame_to_records, run_readonly_sql)
from bizzmind.i18n import req_lang
from bizzmind.localization import _load_i18n, content_lang, localize_charts
from bizzmind.project import get_project

router = APIRouter()

DEMO_PID = "demo-public"
SCRIPT_P = DATA_DIR / "demo_script.json"


def _demo():
    proj = get_project(DEMO_PID)
    proj.reload()
    return proj


@router.get("/api/demo/state")
def demo_state(request: Request):
    """Dashboard, filters and tables of the demo project — no auth, no AI."""
    proj = _demo()
    lang = req_lang(request)
    proj.lang = lang
    charts, filters = proj.dashboard, filters_with_options(proj)
    field_labels: dict = {}
    value_labels: dict = {}
    if lang != content_lang(proj):
        tr = _load_i18n(proj, lang)
        if tr:                       # translated once offline; visitors never pay for AI
            charts, field_labels, value_labels, _ = localize_charts(proj, lang, tr, charts)
            for fl in filters:
                fl["label"] = tr.get(fl.get("label", ""), fl.get("label", ""))
                fl["resolved_options"] = [tr.get(o, o) for o in (fl.get("resolved_options") or [])]
    return {
        "name": proj.meta.get("name", "Demo"),
        "tables": describe_schema(proj),
        "charts": charts,
        "filters": filters,
        "notes": proj.notes,
        "i18n": {"field_labels": field_labels, "value_labels": value_labels,
                 "content_lang": content_lang(proj), "ui_lang": lang, "needs_translation": False},
        "files": [{"filename": f, "tables": t} for f, t in (proj.meta.get("files") or {}).items()],
    }


@router.post("/api/demo/refresh")
async def demo_refresh(request: Request):
    """Re-run the dashboard under the visitor's filter choices (pure SQL)."""
    body = await request.json()
    proj = _demo()
    proj.lang = req_lang(request)
    sel = body.get("selections") or {}
    if not isinstance(sel, dict) or len(sel) > 20:
        raise HTTPException(400, "bad selections")
    import asyncio

    from fastapi.concurrency import run_in_threadpool

    from bizzmind.config import MAX_CHART_ROWS

    def run_one(c):
        chart = dict(c)
        try:
            df = run_readonly_sql(proj, apply_filters_to_sql(proj, c["sql"], sel), MAX_CHART_ROWS)
            chart["rows"] = frame_to_records(df)
        except Exception as e:
            chart["error"] = str(e)
        return chart

    charts = list(await asyncio.gather(*[run_in_threadpool(run_one, c) for c in proj.dashboard]))
    return {"charts": charts, "filters": filters_with_options(proj)}


@router.get("/api/demo/script")
def demo_script():
    """The recorded session (ingest progress, interview, canned answers) that
    the demo page replays — generated once, costs nothing to serve."""
    if not SCRIPT_P.exists():
        return {"steps": [], "questions": []}
    return json.loads(SCRIPT_P.read_text())
