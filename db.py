"""Bizzmind — project data layer on PostgreSQL (Supabase).

Every project gets its own schema (p_<id>) holding the tables imported from the
user's spreadsheets and the semantic views the AI defines. AI-authored SQL runs
through `query_df(..., readonly=True)`, which

  * switches to a NOLOGIN role that can only SELECT inside that one schema
    (so a bad or malicious query cannot touch other projects or write anything),
  * pins search_path to the schema,
  * sets a statement timeout,
  * runs in a READ ONLY transaction.

Configuration: SUPABASE_DB_URL (production) or DATABASE_URL (dev), defaulting
to a local `inceptiq_dev` database.
"""
from __future__ import annotations

import atexit
import logging
import math
import os
import re
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd
import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool

log = logging.getLogger("studio")

DB_URL: str | None = None   # resolved lazily so app.py can load .env first (override for tests)


def db_url() -> str:
    return (DB_URL or os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
            or "postgresql://localhost/inceptiq_dev")


QUERY_TIMEOUT_MS = int(os.environ.get("SQL_TIMEOUT_MS", "20000"))

_pool: ConnectionPool | None = None


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(close)


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(db_url(), min_size=int(os.environ.get("DB_POOL_MIN", "2")),
                               max_size=int(os.environ.get("DB_POOL_MAX", "8")),
                               check=ConnectionPool.check_connection,   # drop connections the pooler closed
                               kwargs={"autocommit": False, "prepare_threshold": None}, open=True)
        log.info(f"db: pool opened -> {re.sub(r':[^:@/]+@', ':***@', db_url())}")
    return _pool


# --------------------------------------------------------------- naming

def schema_for(pid: str) -> str:
    return "p_" + re.sub(r"[^a-z0-9_]", "_", pid.lower())


def role_for(pid: str) -> str:
    return "r_" + re.sub(r"[^a-z0-9_]", "_", pid.lower())


def _ident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


# --------------------------------------------------------------- connections

@contextmanager
def connect(pid: str, readonly: bool = False):
    """Connection scoped to the project's schema. readonly=True also drops
    privileges to the project's read-only role and enforces the timeout.
    The session SETs go out in a single network round trip (pipeline mode) —
    with a remote pooler every round trip costs ~100+ ms."""
    schema = schema_for(pid)
    with pool().connection() as con:
        if readonly:
            stmts = ["SET TRANSACTION READ ONLY",
                     sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(QUERY_TIMEOUT_MS)),
                     sql.SQL("SET LOCAL search_path = {}, pg_catalog").format(_ident(schema)),
                     sql.SQL("SET LOCAL ROLE {}").format(_ident(role_for(pid)))]
        else:
            stmts = [sql.SQL("SET LOCAL search_path = {}, public").format(_ident(schema))]
        try:
            with con.pipeline():
                for st in stmts:
                    con.execute(st)
        except psycopg.Error:
            # role missing (project created before roles existed) — keep schema isolation
            con.rollback()
            with con.pipeline():
                for st in stmts[:-1] if readonly else stmts:
                    con.execute(st)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise


def ensure_project(pid: str) -> None:
    """Create the schema and its read-only role (idempotent)."""
    schema, role = schema_for(pid), role_for(pid)
    with pool().connection() as con:
        con.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(_ident(schema)))
        con.execute(sql.SQL(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {lit}) THEN "
            "CREATE ROLE {role} NOLOGIN; END IF; END $$;"
        ).format(lit=sql.Literal(role), role=_ident(role)))
        con.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(_ident(role)))
        con.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(_ident(schema), _ident(role)))
        con.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(_ident(schema), _ident(role)))
        con.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}")
                    .format(_ident(schema), _ident(role)))
        # DuckDB-compatibility helpers the AI (and legacy dashboards) lean on
        for fn in COMPAT_FUNCTIONS:
            con.execute(sql.SQL(fn).format(s=_ident(schema), lit=sql.Literal(schema)))
        con.execute(sql.SQL("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {} TO {}").format(_ident(schema), _ident(role)))
        con.commit()


COMPAT_FUNCTIONS = [
    # ROUND(double, n) — Postgres only has round(numeric, int)
    "CREATE OR REPLACE FUNCTION {s}.round(double precision, integer) RETURNS numeric "
    "LANGUAGE sql IMMUTABLE SET search_path = '' AS 'SELECT pg_catalog.round($1::numeric, $2)'",
    "CREATE OR REPLACE FUNCTION {s}.round(bigint, integer) RETURNS numeric "
    "LANGUAGE sql IMMUTABLE SET search_path = '' AS 'SELECT pg_catalog.round($1::numeric, $2)'",
]


def drop_project(pid: str) -> None:
    schema, role = schema_for(pid), role_for(pid)
    with pool().connection() as con:
        con.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(_ident(schema)))
        con.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(_ident(role)))
        con.commit()


# --------------------------------------------------------------- catalogue

_TYPE_NAMES = {
    "text": "VARCHAR", "character varying": "VARCHAR", "character": "VARCHAR",
    "double precision": "DOUBLE", "real": "DOUBLE", "numeric": "DECIMAL",
    "bigint": "BIGINT", "integer": "INTEGER", "smallint": "INTEGER",
    "boolean": "BOOLEAN", "date": "DATE",
    "timestamp without time zone": "TIMESTAMP", "timestamp with time zone": "TIMESTAMPTZ",
}


def table_counts() -> dict[str, int]:
    """{project id: number of tables+views} for every project schema in one query."""
    with pool().connection() as con:
        rows = con.execute(
            "SELECT table_schema, count(*) FROM information_schema.tables "
            "WHERE table_schema LIKE 'p\\_%' GROUP BY 1").fetchall()
    return {r[0][2:].replace("_", "-"): r[1] for r in rows}


def has_data(pid: str) -> bool:
    return bool(list_tables(pid))


def list_tables(pid: str) -> list[tuple[str, str]]:
    """[(name, 'table'|'view')] in the project's schema, tables first."""
    with pool().connection() as con:
        rows = con.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_type, table_name", (schema_for(pid),)).fetchall()
    return [(r[0], "view" if "VIEW" in r[1].upper() else "table") for r in rows]


def columns(pid: str, table: str) -> list[tuple[str, str]]:
    """[(column, TYPE)] with DuckDB-style type names the UI/AI already know."""
    with pool().connection() as con:
        rows = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
            (schema_for(pid), table)).fetchall()
    return [(r[0], _TYPE_NAMES.get(r[1], r[1].upper())) for r in rows]


def schema_summary(pid: str) -> list[dict]:
    """[{table, kind, rows, columns:[{name,type}], sample_rows:[...]}] for the
    whole project in three statements (instead of 3 per table)."""
    schema = schema_for(pid)
    tables = list_tables(pid)
    if not tables:
        return []
    with pool().connection() as con:
        cols = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (schema,)).fetchall()
    by_table: dict[str, list] = {}
    for t, c, dt in cols:
        by_table.setdefault(t, []).append({"name": c, "type": _TYPE_NAMES.get(dt, dt.upper())})
    # counts + 2 sample rows per table, one statement each (UNION ALL)
    parts = [sql.SQL("SELECT {lit} AS t, (SELECT count(*) FROM {tbl}) AS n, "
                     "(SELECT json_agg(s) FROM (SELECT * FROM {tbl} LIMIT 2) s) AS sample")
             .format(lit=sql.Literal(t), tbl=_ident(t)) for t, _ in tables]
    stats: dict[str, tuple] = {}
    try:
        with connect(pid, readonly=True) as con:
            for t, n, sample in con.execute(sql.SQL(" UNION ALL ").join(parts)).fetchall():
                stats[t] = (n, sample or [])
    except Exception as e:
        log.info(f"[{pid}] schema stats failed — {e}")
    out = []
    for t, kind in tables:
        n, sample = stats.get(t, (0, []))
        out.append({"table": t, "kind": kind, "rows": n, "columns": by_table.get(t, []),
                    "sample_rows": sample if isinstance(sample, list) else []})
    return out


def row_count(pid: str, table: str) -> int:
    with connect(pid, readonly=True) as con:
        return con.execute(sql.SQL("SELECT count(*) FROM {}").format(_ident(table))).fetchone()[0]


# --------------------------------------------------------------- queries

def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):          # None, NaN, NaT, pd.NA
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and math.isinf(v):
        return None
    return v


def _session_stmts(pid: str, readonly: bool, with_role: bool = True) -> list:
    schema = schema_for(pid)
    if not readonly:
        return [sql.SQL("SET LOCAL search_path = {}, public").format(_ident(schema))]
    stmts = ["SET TRANSACTION READ ONLY",
             sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(QUERY_TIMEOUT_MS)),
             sql.SQL("SET LOCAL search_path = {}, pg_catalog").format(_ident(schema))]
    if with_role:
        stmts.append(sql.SQL("SET LOCAL ROLE {}").format(_ident(role_for(pid))))
    return stmts


def query_df(pid: str, query: str, params=None, limit: int | None = None,
             readonly: bool = True) -> pd.DataFrame:
    """Session SETs + the query + COMMIT travel in a single pipeline round trip."""
    with pool().connection() as con:
        for with_role in (True, False):
            try:
                with con.pipeline():
                    for st in _session_stmts(pid, readonly, with_role):
                        con.execute(st)
                    cur = con.execute(query, params)
                    con.execute("COMMIT")
                break
            except psycopg.Error as e:
                con.rollback()
                # missing per-project role -> retry without SET ROLE (schema isolation still holds)
                if with_role and "role" in str(e).lower() and "does not exist" in str(e).lower():
                    continue
                raise
        cols = [c.name for c in cur.description] if cur.description else []
        rows = cur.fetchmany(limit) if limit else cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def execute(pid: str, query, params=None) -> None:
    with connect(pid, readonly=False) as con:
        con.execute(query, params)


def create_view(pid: str, name: str, body: str) -> None:
    execute(pid, sql.SQL("CREATE OR REPLACE VIEW {} AS {}").format(_ident(name), sql.SQL(body)))


def drop_view(pid: str, name: str) -> None:
    execute(pid, sql.SQL("DROP VIEW IF EXISTS {} CASCADE").format(_ident(name)))


def drop_table(pid: str, name: str) -> None:
    execute(pid, sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(_ident(name)))


# --------------------------------------------------------------- import

def _pg_type(s: pd.Series) -> str:
    dt = s.dtype
    if pd.api.types.is_bool_dtype(dt):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dt):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dt):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(dt):
        return "TIMESTAMP"
    if dt == object:
        non_null = s.dropna()
        if len(non_null) and all(isinstance(v, (date, datetime)) for v in non_null.head(50)):
            return "TIMESTAMP"
    return "TEXT"


def load_frame(pid: str, table: str, df: pd.DataFrame, replace: bool = True) -> int:
    """Create (or replace) a table from a DataFrame and bulk-load it with COPY."""
    ensure_project(pid)
    cols = [str(c) for c in df.columns]
    types = [_pg_type(df.iloc[:, i]) for i in range(df.shape[1])]
    with connect(pid, readonly=False) as con:
        if replace:
            con.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(_ident(table)))
        con.execute(sql.SQL("CREATE TABLE {} ({})").format(
            _ident(table),
            sql.SQL(", ").join(sql.SQL("{} {}").format(_ident(c), sql.SQL(t)) for c, t in zip(cols, types))))
        with con.cursor() as cur:
            with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(
                    _ident(table), sql.SQL(", ").join(_ident(c) for c in cols))) as copy:
                copy.set_types([_copy_type(t) for t in types])
                for row in df.itertuples(index=False, name=None):
                    copy.write_row([_coerce(v, t) for v, t in zip(row, types)])
    return len(df)


def _copy_type(t: str) -> str:
    return {"BOOLEAN": "bool", "BIGINT": "int8", "DOUBLE PRECISION": "float8",
            "TIMESTAMP": "timestamp", "TEXT": "text"}[t]


def _coerce(v, t: str):
    v = _clean(v)
    if v is None or (isinstance(v, str) and v == "" and t != "TEXT"):
        return None
    if t == "TEXT":
        return v if isinstance(v, str) else str(v)
    if t == "BIGINT":
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    if t == "DOUBLE PRECISION":
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    if t == "TIMESTAMP":
        if isinstance(v, pd.Timestamp):
            return None if pd.isna(v) else v.to_pydatetime()
        return v if isinstance(v, (datetime, date)) else None
    if t == "BOOLEAN":
        return bool(v)
    return v


# --------------------------------------------------------------- project metadata
# public.projects holds everything that used to live in per-project JSON files
# (meta/dashboard/filters/notes/chat/i18n/progress). Written with the service
# connection; RLS guards direct client access.
from psycopg.types.json import Jsonb  # noqa: E402

PROJECT_COLS = ("meta", "dashboard", "filters", "notes", "chat", "i18n", "progress")


def project_load(pid: str) -> dict | None:
    with pool().connection() as con:
        row = con.execute(
            "SELECT id, org_id, name, created_at, meta, dashboard, filters, notes, chat, i18n, progress "
            "FROM public.projects WHERE id = %s", (pid,)).fetchone()
    if not row:
        return None
    keys = ("id", "org_id", "name", "created_at", "meta", "dashboard", "filters", "notes", "chat", "i18n", "progress")
    return dict(zip(keys, row))


def project_exists(pid: str) -> bool:
    with pool().connection() as con:
        return con.execute("SELECT 1 FROM public.projects WHERE id = %s", (pid,)).fetchone() is not None


def project_create(pid: str, name: str, org_id=None, **cols) -> None:
    payload = {k: cols.get(k) for k in PROJECT_COLS if k in cols}
    with pool().connection() as con:
        con.execute(
            "INSERT INTO public.projects (id, org_id, name, meta, dashboard, filters, notes, chat, i18n, progress) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (pid, org_id, name,
             Jsonb(payload.get("meta") or {}), Jsonb(payload.get("dashboard") or []),
             Jsonb(payload.get("filters") or []), Jsonb(payload.get("notes") or []),
             Jsonb(payload.get("chat") or []), Jsonb(payload.get("i18n") or {}),
             payload.get("progress")))
        con.commit()


def project_save(pid: str, **cols) -> None:
    sets, vals = [], []
    for k, v in cols.items():
        if k == "name":
            sets.append("name = %s"); vals.append(v)
        elif k == "progress":
            sets.append("progress = %s"); vals.append(v)
        elif k in PROJECT_COLS:
            sets.append(f"{k} = %s"); vals.append(Jsonb(v))
    if not sets:
        return
    with pool().connection() as con:
        con.execute(f"UPDATE public.projects SET {', '.join(sets)} WHERE id = %s", (*vals, pid))
        con.commit()


def project_delete(pid: str) -> None:
    with pool().connection() as con:
        con.execute("DELETE FROM public.projects WHERE id = %s", (pid,))
        con.commit()


def project_list(org_id=None) -> list[dict]:
    q = ("SELECT id, name, created_at, jsonb_array_length(dashboard), jsonb_array_length(notes), org_id, "
         "(SELECT coalesce(sum(jsonb_array_length(v)), 0) FROM jsonb_each(coalesce(meta->'files', '{}'::jsonb)) AS f(k, v)) "
         "FROM public.projects" + (" WHERE org_id = %s" if org_id else "") + " ORDER BY created_at")
    with pool().connection() as con:
        rows = con.execute(q, (org_id,) if org_id else None).fetchall()
    return [{"id": r[0], "name": r[1], "created": r[2].strftime("%Y-%m-%d") if r[2] else "",
             "charts": r[3], "notes": r[4], "org_id": str(r[5]) if r[5] else None, "tables": int(r[6] or 0)}
            for r in rows]


def default_org() -> str:
    """The single organisation used until Supabase Auth / multi-tenant onboarding lands."""
    with pool().connection() as con:
        row = con.execute("SELECT id FROM public.organizations ORDER BY created_at LIMIT 1").fetchone()
        if row:
            return str(row[0])
        row = con.execute("INSERT INTO public.organizations (name) VALUES ('Inceptiq') RETURNING id").fetchone()
        con.commit()
        return str(row[0])
