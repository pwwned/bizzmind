"""Plans, limits and the unified credit pool.

One credit currency for the whole product; different actions cost a different
number of credits. The per-action breakdown lives in public.credit_events so
usage can be reported split (analyses vs presentations) without separate pools.
Volume-first pricing (the Gamma model): credits are cheap in bulk, actions
draw visibly large amounts. Anchor: EUR 20 -> 4000 credits (~EUR 0.005/cr).
"""
from __future__ import annotations

from fastapi import HTTPException

from bizzmind.i18n import T
from db import pool

PLANS = {
    "free":  {"label": "Free",  "price_eur": 0,   "projects": 1,  "files_per_project": 2,
              "max_file_mb": 5,   "credits": 1000,  "monthly": False},
    "pro":   {"label": "Pro",   "price_eur": 25,  "projects": 10, "files_per_project": 50,
              "max_file_mb": 25,  "credits": 4000,  "monthly": True},
    "ultra": {"label": "Ultra", "price_eur": 99, "projects": 50, "files_per_project": 200,
              "max_file_mb": 100, "credits": 20000, "monthly": True},
}

# The user picks the model per project; each burns credits differently.
MODELS = {
    "standard": {"label": "Standard", "model_id": "claude-sonnet-5", "min_plan": "free"},
    "max":      {"label": "Max",      "model_id": "claude-opus-5",   "min_plan": "pro"},
}

COSTS = {
    "analysis":     {"standard": 500, "max": 1200},
    "chat":         {"standard": 40,  "max": 100},
    "presentation": {"standard": 200, "max": 200},   # engine cost does not depend on the model
}


def norm_model(model: str | None) -> str:
    return model if model in MODELS else "standard"


def cost_of(kind: str, model: str | None = None) -> int:
    return COSTS[kind][norm_model(model)]


def model_allowed(plan: str, model: str | None) -> bool:
    return MODELS[norm_model(model)]["min_plan"] == "free" or plan != "free"

# top-up packs: the bigger the pack, the better the rate
PACKS = [
    {"credits": 1000,  "price_eur": 7},
    {"credits": 4000,  "price_eur": 20},
    {"credits": 10000, "price_eur": 40},
]


def org_of_project(pid: str):
    with pool().connection() as con:
        row = con.execute("SELECT org_id FROM public.projects WHERE id = %s", (pid,)).fetchone()
    return row[0] if row else None


def _renew_if_due(con, org_id) -> None:
    """Gamma-style rollover: on each monthly renewal the unused part of the
    plan allowance carries over, capped at 2x the monthly amount. Purchased
    top-ups (credits_extra) never expire. Lazy until a billing cycle exists."""
    row = con.execute(
        "SELECT plan, credits_quota, credits_used, credits_renewed_at "
        "FROM public.organizations WHERE id = %s "
        "AND credits_renewed_at < now() - interval '30 days'", (org_id,)).fetchone()
    if not row:
        return
    plan, quota, used, _ = row
    p = PLANS.get(plan, PLANS["free"])
    if not p["monthly"]:
        return
    monthly = p["credits"]
    new_quota = min(max(0, quota - used) + monthly, 2 * monthly)
    con.execute("UPDATE public.organizations SET credits_quota = %s, credits_used = 0, "
                "credits_renewed_at = now() WHERE id = %s", (new_quota, org_id))


def org_state(org_id) -> dict:
    with pool().connection() as con:
        _renew_if_due(con, org_id)
        row = con.execute(
            "SELECT plan, credits_quota, credits_extra, credits_used, auto_recharge, name "
            "FROM public.organizations WHERE id = %s", (org_id,)).fetchone()
    if not row:
        return {"plan": "free", "quota": 0, "extra": 0, "used": 0,
                "remaining": 0, "auto_recharge": False, "org_name": ""}
    plan, quota, extra, used, auto, name = row
    if plan not in PLANS:
        plan = "free"
    return {"plan": plan, "quota": quota, "extra": extra, "used": used,
            "remaining": max(0, quota + extra - used), "auto_recharge": auto, "org_name": name}


def limits_of(plan: str) -> dict:
    return PLANS.get(plan, PLANS["free"])


def project_count(org_id) -> int:
    with pool().connection() as con:
        return con.execute("SELECT count(*) FROM public.projects WHERE org_id = %s",
                           (org_id,)).fetchone()[0]


def ensure_can_afford(pid: str, kind: str, lang: str, model: str | None = None) -> None:
    """Pre-flight check (no deduction) — used before spending on the engine."""
    org = org_of_project(pid)
    if org is None:
        return
    st = org_state(org)
    if not model_allowed(st["plan"], model):
        raise HTTPException(403, T(lang, "model_not_in_plan"))
    if st["remaining"] < cost_of(kind, model):
        raise HTTPException(402, T(lang, "no_credits"))


def charge(pid: str, kind: str, lang: str, model: str | None = None) -> None:
    """Deduct the action's price atomically; 402 when the pool can't cover it."""
    org = org_of_project(pid)
    if org is None:
        return
    if not model_allowed(org_state(org)["plan"], model):
        raise HTTPException(403, T(lang, "model_not_in_plan"))
    cost = cost_of(kind, model)
    with pool().connection() as con:
        row = con.execute(
            "UPDATE public.organizations SET credits_used = credits_used + %s "
            "WHERE id = %s AND credits_used + %s <= credits_quota + credits_extra "
            "RETURNING 1", (cost, org, cost)).fetchone()
        if not row:
            raise HTTPException(402, T(lang, "no_credits"))
        con.execute("INSERT INTO public.credit_events (org_id, project_id, kind, credits) "
                    "VALUES (%s, %s, %s, %s)", (org, pid, kind, cost))


def usage_breakdown(org_id) -> list[dict]:
    with pool().connection() as con:
        rows = con.execute(
            "SELECT kind, count(*), sum(credits) FROM public.credit_events "
            "WHERE org_id = %s GROUP BY kind ORDER BY sum(credits) DESC", (org_id,)).fetchall()
    return [{"kind": k, "count": n, "credits": c} for k, n, c in rows]
