"""Inceptiq Analytics — project data layer on PostgreSQL (Supabase).

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

DB_URL = (os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
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
        _pool = ConnectionPool(DB_URL, min_size=1, max_size=int(os.environ.get("DB_POOL_MAX", "8")),
                               kwargs={"autocommit": False}, open=True)
        log.info(f"db: pool opened -> {re.sub(r':[^:@/]+@', ':***@', DB_URL)}")
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
    privileges to the project's read-only role and enforces the timeout."""
    schema = schema_for(pid)
    with pool().connection() as con:
        with con.cursor() as cur:
            if readonly:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(QUERY_TIMEOUT_MS)))
                cur.execute(sql.SQL("SET LOCAL search_path = {}, pg_catalog").format(_ident(schema)))
                try:
                    cur.execute(sql.SQL("SET LOCAL ROLE {}").format(_ident(role_for(pid))))
                except psycopg.Error:
                    # role missing (project created before roles existed) — schema
                    # isolation still holds through search_path; ensure_project() repairs it
                    con.rollback()
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(QUERY_TIMEOUT_MS)))
                    cur.execute(sql.SQL("SET LOCAL search_path = {}, pg_catalog").format(_ident(schema)))
            else:
                cur.execute(sql.SQL("SET LOCAL search_path = {}, public").format(_ident(schema)))
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
    "LANGUAGE sql IMMUTABLE AS 'SELECT round($1::numeric, $2)'",
    "CREATE OR REPLACE FUNCTION {s}.round(bigint, integer) RETURNS numeric "
    "LANGUAGE sql IMMUTABLE AS 'SELECT round($1::numeric, $2)'",
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


def query_df(pid: str, query: str, params=None, limit: int | None = None,
             readonly: bool = True) -> pd.DataFrame:
    with connect(pid, readonly=readonly) as con:
        cur = con.execute(query, params)
        cols = [d.name for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit) if limit else cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    return df


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
    types = [_pg_type(df[c]) for c in df.columns]
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
