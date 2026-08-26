"""AI agent: prompts, tool schema/execution, subscription (Agent SDK) and API
backends, and the long-running tasks built on them (review, deck, translate)."""

from __future__ import annotations

import asyncio
import json
import re
import time

import db
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from bizzmind.config import (AI_BACKEND, MAX_CHART_ROWS, MAX_PREVIEW_ROWS, MAX_SERIES, MODEL,
                             SUB_TIMEOUT_S, _short, log)
from bizzmind.i18n import LANG_NAMES, T
from bizzmind.project import Project, write_progress
from bizzmind.data import (invalidate, FORBIDDEN_SQL, apply_filters_to_sql, describe_schema, frame_to_records,
                           pg_compat, resolve_filter_options, run_readonly_sql, verify_dashboard)
from bizzmind.brand import brand_excerpt, brand_files
from bizzmind.localization import _h, _load_i18n, _save_i18n, content_lang, translatable_items

# The Claude Agent SDK (local subscription mode) is optional: production runs on
# the Anthropic API and the SDK — which bundles the Claude Code CLI — is not
# installed there (see requirements-dev.txt).
try:
    from claude_agent_sdk import (  # noqa: E402
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        TextBlock,
        create_sdk_mcp_server,
        tool,
    )
    SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    SDK_AVAILABLE = False
    AssistantMessage = ClaudeAgentOptions = ClaudeSDKClient = ResultMessage = TextBlock = None  # type: ignore

    def tool(*_a, **_k):  # type: ignore
        return lambda f: f

    def create_sdk_mcp_server(*_a, **_k):  # type: ignore
        return None


_client = None


class _LazyClient:
    """anthropic.Anthropic() needs ANTHROPIC_API_KEY at construction (and the
    import costs ~0.3 s on a cold start) — create it on first use."""
    def __getattr__(self, name):
        global _client
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic()
        return getattr(_client, name)


client = _LazyClient()


def conversation_recap(proj: Project, limit: int = 14) -> str:
    if not proj.chat:
        return ""
    who = {"user": "User", "ai": "You (assistant)", "event": "Event"}
    lines = [f"{who.get(m['role'], m['role'])}: {_short(m['text'], 400)}" for m in proj.chat[-limit:]]
    return ("<conversation_recap>\nThe app restarted. This is the recent conversation — "
            "continue from here; do NOT restart the interview or re-ask answered questions:\n"
            + "\n".join(lines) + "\n</conversation_recap>\n\n")


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
                invalidate(proj.id)
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
                invalidate(proj.id)
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
    if not SDK_AVAILABLE:
        raise RuntimeError("Claude Agent SDK is not installed — set AI_BACKEND=api with ANTHROPIC_API_KEY")
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
    import anthropic  # lazy: heavy import, only needed in API mode
    """Production path: Anthropic API with a manual tool loop."""
    if not proj.messages:  # fresh process: continue from the stored transcript
        user_content = conversation_recap(proj) + user_content
    proj.messages.append({"role": "user", "content": user_content})
    proj.new_charts.clear()
    proj.new_questions = []

    while True:
        try:
            response = client.beta.messages.create(
                model=getattr(proj, "ai_model_id", None) or MODEL,
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


async def run_translate(proj: Project):
    lang = proj.lang
    pid = proj.id
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
        _save_i18n(proj, lang, tr)
    # drop entries whose source text no longer exists (keeps the file small)
    tr = {k: v for k, v in tr.items() if k in items}
    _save_i18n(proj, lang, tr)
    log.info(f"[{pid}] i18n: done — {done}/{len(missing)} translated")
    proj.log_activity("info", T(lang, "act_translated", n=done))
    return {"translated": done, "missing": len(missing) - done, "content_lang": src,
            "reply": T(lang, "act_translated", n=done)}


async def run_review(proj: Project, tables: list, context: str = "", goal: str = ""):
    lang = proj.lang
    proj.add_chat("event", T(lang, "chat_files_loaded", tables=', '.join(tables)))
    upfront = ""
    if context.strip() or goal.strip():
        parts = []
        if context.strip():
            parts.append(T(lang, "chat_context", text=context.strip()))
        if goal.strip():
            parts.append(T(lang, "chat_goal", text=goal.strip()))
        user_text = "\n".join(parts)
        proj.add_chat("user", user_text)
        upfront = (f"\nThe user provided this upfront — treat it as answered "
                   f"interview ground truth, record every durable fact and goal "
                   f"with record_data_context, and do NOT re-ask about any of it:\n"
                   f"{user_text}\n")
    return await dispatch_agent(
        proj,
        f"[The user just uploaded file(s) loaded as: {', '.join(tables)}.{upfront}"
        "Follow your interview-mode instructions: investigate the new data, "
        "say briefly what you understood, and ask only the clarifying "
        "questions you really need (skip anything already answered above). "
        "Address the user directly.]"
    )


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


async def run_deck(proj: Project):
    lang = proj.lang
    pid = proj.id
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
        raise RuntimeError(T(lang, "err_deck_invalid"))
    try:
        spec = json.loads(m.group(0))
    except Exception:
        raise RuntimeError(T(lang, "err_deck_json"))
    log.info(f"[{pid}] deck: done in {time.monotonic() - t0:.1f}s — "
             f"{sum(len(s.get('slides', [])) for s in spec.get('sections', []))} слайда, "
             f"{len(spec.get('sections', []))} секции")
    g = spec.get("gamma") or {}
    if g.get("audience"):
        log.info(f"[{pid}] deck: brief — аудитория: {_short(g.get('audience'), 80)} | тон: {_short(g.get('tone'), 60)}")
    proj.add_chat("ai", T(lang, "chat_deck_ready"))
    return {"spec": spec}
