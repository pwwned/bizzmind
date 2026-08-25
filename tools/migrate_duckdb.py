"""Migrate legacy per-project DuckDB files into PostgreSQL (Supabase).

  .venv/bin/python tools/migrate_duckdb.py            # all projects under data/projects
  .venv/bin/python tools/migrate_duckdb.py poli-demo  # one project

For every project: tables -> Postgres schema p_<id> (COPY), views recreated
from their DuckDB definition when Postgres accepts them, then every chart /
filter SQL is test-run. Whatever fails is listed so the AI (or you) can
translate it — nothing in dashboard.json is changed by this script.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import duckdb  # noqa: E402  (legacy reader only)
import db      # noqa: E402

PROJECTS = ROOT / "data" / "projects"


def migrate(pid: str) -> dict:
    pdir = PROJECTS / pid
    dpath = pdir / "project.duckdb"
    report = {"project": pid, "tables": [], "views_ok": [], "views_failed": [],
              "charts_failed": [], "filters_failed": []}
    if not dpath.exists():
        report["skipped"] = "no DuckDB file"
        return report
    db.ensure_project(pid)
    con = duckdb.connect(str(dpath), read_only=True)
    try:
        objs = con.execute("SELECT table_name, table_type FROM information_schema.tables "
                           "WHERE table_schema='main' ORDER BY table_type DESC, table_name").fetchall()
        for name, ttype in objs:
            if "VIEW" in ttype.upper():
                continue
            df = con.execute(f'SELECT * FROM "{name}"').fetchdf()
            n = db.load_frame(pid, name, df)
            report["tables"].append((name, n))
            print(f"  table {name}: {n} rows")
        for name, ttype in objs:
            if "VIEW" not in ttype.upper():
                continue
            body = con.execute("SELECT sql FROM duckdb_views() WHERE view_name = ?", [name]).fetchone()
            body = body[0] if body else ""
            # duckdb stores 'CREATE VIEW name AS SELECT …;'
            sel = body.split(" AS ", 1)[1].rstrip(";") if " AS " in body else ""
            try:
                db.create_view(pid, name, sel)
                report["views_ok"].append(name)
            except Exception as e:
                report["views_failed"].append((name, str(e).splitlines()[0]))
    finally:
        con.close()

    def _load(name):
        p = pdir / name
        return json.loads(p.read_text()) if p.exists() else []
    import app  # noqa: E402  — for apply_filters_to_sql & run_readonly_sql
    proj = app.get_project(pid)
    for c in _load("dashboard.json"):
        try:
            app.run_readonly_sql(proj, app.apply_filters_to_sql(proj, c["sql"], {}), 5)
        except Exception as e:
            report["charts_failed"].append((c["id"], c["title"][:50], str(e)[:140]))
    for f in _load("filters.json"):
        if f.get("options_sql"):
            try:
                app.run_readonly_sql(proj, f["options_sql"], 5)
            except Exception as e:
                report["filters_failed"].append((f["id"], str(e)[:140]))
    return report


if __name__ == "__main__" and "--ai" not in sys.argv:
    pids = sys.argv[1:] or [p.name for p in sorted(PROJECTS.iterdir()) if (p / "project.duckdb").exists()]
    for pid in pids:
        print(f"== {pid}")
        r = migrate(pid)
        print(json.dumps({k: v for k, v in r.items() if k != "tables"}, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- AI pass
SQL_FIX_PROMPT = """[Task: this dashboard chart was written for DuckDB and fails on PostgreSQL.
Rewrite ONLY the SQL so it runs on PostgreSQL and returns the same columns
(same names, same meaning, same ordering intent). Keep the {{{{filter_id}}}} tokens exactly
where they are — they are replaced by the app with boolean conditions or a single value.
Replace DuckDB-only features: UNPIVOT/COLUMNS(regex) -> a UNION ALL of the listed month
columns, or unnest(ARRAY[...]) WITH ORDINALITY; PIVOT -> conditional aggregates;
format()/printf -> to_char/concat; list functions -> array functions; every non-aggregated
column into GROUP BY; explicit ::numeric casts. Use run_sql_query to test your rewrite
(the tokens will be expanded) before you answer, and iterate until it runs and the
declared x/y fields are present.
Chart: {title}
x_field: {x}   y_fields: {ys}
PostgreSQL error: {err}
Original SQL:
{sql}

Return ONLY the final SQL — no markdown fences, no commentary.]"""


async def ai_fix(pid: str, only_failed: bool = True):
    import app
    proj = app.get_project(pid)
    fixed, still = 0, []
    for c in proj.dashboard:
        try:
            app.run_readonly_sql(proj, app.apply_filters_to_sql(proj, c["sql"], {}), 5)
            continue
        except Exception as e:
            err = str(e)[:300]
        print(f"  fixing #{c['id']} {c['title'][:50]} — {err[:80]}")
        prompt = SQL_FIX_PROMPT.format(title=c["title"], x=c.get("x_field"), ys=c.get("y_fields"),
                                       err=err, sql=c["sql"])
        result = await app.run_agent_subscription(proj, prompt)
        new_sql = result["reply"].strip()
        new_sql = new_sql.strip("`").replace("```sql", "").replace("```", "").strip()
        try:
            df = app.run_readonly_sql(proj, app.apply_filters_to_sql(proj, new_sql, {}), 5)
            missing = [x for x in [c.get("x_field"), *(c.get("y_fields") or [])] if x and x not in df.columns]
            if missing:
                raise ValueError(f"fields missing after rewrite: {missing}")
            c["sql"] = new_sql
            proj.save_dash()
            fixed += 1
            print(f"    ok ({len(df.columns)} cols)")
        except Exception as e:
            still.append((c["id"], str(e)[:120]))
            print(f"    still failing: {str(e)[:120]}")
    return fixed, still


if __name__ == "__main__" and "--ai" in sys.argv:
    import asyncio
    for pid in [a for a in sys.argv[1:] if not a.startswith("--")]:
        print(f"== AI fix {pid}")
        print(asyncio.run(ai_fix(pid)))
