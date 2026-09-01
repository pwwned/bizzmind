"""The render is billed from what the engine reports, once, no matter how many
times the status is polled."""
from datetime import datetime, timezone

from bizzmind import gamma, plans


def _setup(monkeypatch, fake_pool, deducted, rows_after_claim=(0,)):
    calls = {"settle": [], "charge": []}
    state = {"claimed": False}

    def respond(sql, p):
        if sql.startswith("SELECT org_id, project_id, created_at"):
            return [("org-1", "proj-1", datetime.now(timezone.utc))], 0
        if sql.startswith("UPDATE public.pres_generations"):
            rc = 0 if state["claimed"] else 1          # the NULL -> value transition happens once
            state["claimed"] = True
            return [], rc
        if "sum(credits)" in sql:
            return [(50,)], 0
        return [], 0

    pool = fake_pool(respond)
    monkeypatch.setattr(gamma, "pool", lambda: pool)
    monkeypatch.setattr(gamma, "_gamma_call", lambda m, path, **kw: {
        "status": "completed", "gammaUrl": "https://gamma.app/docs/x",
        "credits": ({"deducted": deducted} if deducted is not None else None)})
    monkeypatch.setattr(plans, "settle", lambda *a: calls["settle"].append(a) or 50)
    monkeypatch.setattr(plans, "charge", lambda *a: calls["charge"].append(a))
    monkeypatch.setattr(plans, "org_state", lambda org: {"remaining": 4950})
    return calls, pool


def test_render_is_settled_once_at_engine_cost(monkeypatch, fake_pool):
    calls, pool = _setup(monkeypatch, fake_pool, deducted=39)
    first = gamma.gamma_status("gid-1")
    gamma.gamma_status("gid-1")
    gamma.gamma_status("gid-1")
    assert len(calls["settle"]) == 1
    pid, kind, usd, estimate = calls["settle"][0]
    assert (pid, kind) == ("proj-1", "presentation")
    assert usd == plans.engine_cost_usd(39) and estimate == plans.cost_of("presentation")
    assert calls["charge"] == []
    assert first["credits"] == {"deducted": 50, "remaining": 4950}


def test_silent_engine_is_billed_the_quote_not_given_away(monkeypatch, fake_pool):
    calls, _ = _setup(monkeypatch, fake_pool, deducted=None)
    gamma.gamma_status("gid-2")
    gamma.gamma_status("gid-2")
    assert calls["settle"] == []
    assert calls["charge"] == [("proj-1", "presentation", "bg")]


def test_unfinished_generation_costs_nothing(monkeypatch, fake_pool):
    calls, pool = _setup(monkeypatch, fake_pool, deducted=39)
    monkeypatch.setattr(gamma, "_gamma_call", lambda m, path, **kw: {"status": "pending"})
    out = gamma.gamma_status("gid-3")
    assert out["credits"] is None and calls["settle"] == [] and pool.log == []
