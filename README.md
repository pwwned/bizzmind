# AI Analytics Studio — prototype

Drag-and-drop Excel/CSV files, describe what you want to see in plain language,
and an AI builds you a live dashboard. This is the working prototype of the
core pipeline for the SaaS product idea:

**Excel upload → DuckDB → natural-language chat → AI-generated SQL + chart
specs → interactive dashboard.**

## How to run

```bash
# one-time setup (already done if .venv exists)
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# start the app
.venv/bin/uvicorn app:app --port 8000
```

Then open **http://127.0.0.1:8000** in your browser.

**AI backend** (env var `AI_BACKEND`):

- `subscription` (default) — runs through the Claude Agent SDK using your
  local Claude Code login, i.e. your Claude subscription. **For your own
  local testing only** — customer-facing usage must not run on a personal
  subscription.
- `api` — production path via the Anthropic API (`claude-opus-5`). Uses your
  `ant auth login` profile or `ANTHROPIC_API_KEY`; the account needs API
  credits (console.anthropic.com → Plans & Billing).

```bash
AI_BACKEND=api .venv/bin/uvicorn app:app --port 8000
```

## Try it

Drop `sample_data/pharma_sales_2026.xlsx` (a generated demo dataset: 8 sales
reps, 5 products, 4 regions, 12 months) onto the upload zone, then ask things
like:

- "Give me a quick overview dashboard of this data"
- "Show monthly revenue trend and total revenue by region"
- "Which reps are below their revenue target?"
- "Compare product categories over the winter months"

## How it works

| Piece | Where | What it does |
|---|---|---|
| Ingestion | `app.py` → `/api/upload` | Parses Excel/CSV with pandas (each sheet becomes a table), sanitizes names, loads into `data/project.duckdb` |
| Schema summary | `describe_schema()` | Sends the AI only column names, types, and 3 sample rows — never the full data (keeps cost at cents per conversation) |
| AI loop | `/api/chat` | Claude (`claude-opus-5`) with two strict-schema tools: `run_sql_query` (read-only exploration) and `create_chart` (adds a chart to the dashboard). Server-side refusal fallbacks are enabled. |
| Safety | `run_readonly_sql()` | Read-only DuckDB connection + SQL keyword guard; the AI can never modify data |
| Frontend | `static/index.html` | Drag-drop upload, chat panel, ECharts dashboard with a colorblind-validated palette, light + dark mode |

Charts persist in `data/dashboard.json`; the conversation is in-memory
(restarting the server starts a fresh conversation, keeps the charts).

## What this prototype deliberately skips (the product roadmap)

- Multi-user accounts, projects, and Stripe subscriptions
- Multi-file joins and scheduled data refresh
- PowerPoint export (mechanical: render each stored chart spec to an image,
  one slide per chart, AI writes the headline takeaway — the specs are
  already stored in `dashboard.json` for exactly this)
- Editing/deleting individual charts, dashboard layout control
- Streaming responses in the chat UI
