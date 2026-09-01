"""A finished job is billed under the right kind from the cost the run recorded."""
from bizzmind import plans
from bizzmind.routes import projects


def _run(monkeypatch, fake_pool, kind, payload, app_touched=False, cost=2.705):
    pool = fake_pool(lambda sql, p: ([(cost,)], 0) if "cost_usd" in sql else ([], 0))
    monkeypatch.setattr(projects.db, "pool", lambda: pool)
    calls = []
    monkeypatch.setattr(plans, "settle", lambda *a: calls.append(a) or 50)
    projects._settle_job("p1", "job-1", kind, payload, app_touched)
    return calls


def test_chat_is_settled_against_its_estimate_and_model(monkeypatch, fake_pool):
    calls = _run(monkeypatch, fake_pool, "chat", {"estimate": 100, "model": "max"})
    assert calls == [("p1", "chat", 2.705, 100, "max")]


def test_review_bills_as_analysis_and_chat_edits_of_the_app_bill_as_app(monkeypatch, fake_pool):
    assert _run(monkeypatch, fake_pool, "review", {"estimate": 500})[0][1] == "analysis"
    assert _run(monkeypatch, fake_pool, "chat", {"estimate": 40}, app_touched=True)[0][1] == "app"
    assert _run(monkeypatch, fake_pool, "deck", {"estimate": 300})[0][1] == "deck"


def test_ingest_and_proposals_are_never_billed(monkeypatch, fake_pool):
    assert _run(monkeypatch, fake_pool, "ingest", {}) == []
    assert _run(monkeypatch, fake_pool, "app_plan", {}) == []
    assert _run(monkeypatch, fake_pool, "translate", {}) == []


def test_missing_estimate_means_uncapped_not_crash(monkeypatch, fake_pool):
    calls = _run(monkeypatch, fake_pool, "deck", {})
    assert calls[0][3] == 0
