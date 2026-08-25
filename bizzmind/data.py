"""Ingestion, schema description, read-only SQL, dynamic filters, verification."""

from __future__ import annotations

import time

import decimal
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import db
import pandas as pd
from fastapi import HTTPException

from bizzmind.config import MAX_CHART_ROWS, _short, log

if TYPE_CHECKING:
    from bizzmind.project import Project


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


# Per-project caches of things that only change when the data changes
# (uploads, views, edits). Remote Postgres makes every round trip ~100+ ms,
# so /state must not re-derive the schema on each call. TTL guards against
# changes made by other processes (the worker) between invalidations.
_SCHEMA_CACHE: dict[str, tuple[float, list]] = {}
_OPTIONS_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_S = 45.0


def invalidate(pid: str) -> None:
    _SCHEMA_CACHE.pop(pid, None)
    _OPTIONS_CACHE.pop(pid, None)


def describe_schema(proj: Project) -> list:
    """Compact schema summary sent to the model: tables and semantic views,
    with columns and samples. Views carry their stored business description.
    Three round trips for the whole project, cached per project."""
    hit = _SCHEMA_CACHE.get(proj.id)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        summary = db.schema_summary(proj.id)
    except Exception as e:
        log.info(f"[{proj.id}] schema: {_short(e)}")
        return []
    view_meta = proj.meta.get("views", {})
    for entry in summary:
        if entry["kind"] == "view" and entry["table"] in view_meta:
            entry["description"] = view_meta[entry["table"]]
    _SCHEMA_CACHE[proj.id] = (time.time() + CACHE_TTL_S, summary)
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
        cache = _OPTIONS_CACHE.get(proj.id)
        if cache and cache[0] > time.time() and f["id"] in cache[1]:
            return cache[1][f["id"]]
        try:
            df = run_readonly_sql(proj, f["options_sql"], 300)
            opts = [str(v) for v in df.iloc[:, 0].dropna().tolist()]
        except Exception:
            opts = []
        if not cache or cache[0] <= time.time():
            cache = (time.time() + CACHE_TTL_S, {})
        cache[1][f["id"]] = opts
        _OPTIONS_CACHE[proj.id] = cache
        return opts
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
