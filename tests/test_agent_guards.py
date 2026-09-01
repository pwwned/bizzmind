"""The guards that keep one chat message from running away: the shared turn
ceiling and the stop after repeated failed dashboard checks."""
import json

from bizzmind import agent


def test_both_backends_share_one_turn_ceiling():
    assert agent.MAX_TURNS == 40
    assert agent.MAX_VERIFY_RETRIES == 3


def test_repeated_failed_checks_tell_the_agent_to_stop(monkeypatch, fake_project):
    proj = fake_project()
    monkeypatch.setattr(agent, "verify_dashboard", lambda p: {"ok": False, "errors": ["chart #11 fails"]})
    results = [agent._execute_tool_inner(proj, "verify_dashboard", {}) for _ in range(3)]
    assert all(is_err for _, is_err in results)
    first, second, third = (json.loads(r) for r, _ in results)
    assert "stop" not in first and "stop" not in second
    assert "stop" in third and "do NOT call verify_dashboard again" in third["stop"]
    assert proj.verify_fails == 3
    assert any(kind == "error" for kind, _ in proj.activity)


def test_a_passing_check_resets_the_failure_count(monkeypatch, fake_project):
    proj = fake_project(verify_fails=2)
    monkeypatch.setattr(agent, "verify_dashboard", lambda p: {"ok": True, "errors": [], "warnings": []})
    content, is_err = agent._execute_tool_inner(proj, "verify_dashboard", {})
    assert not is_err and proj.verify_fails == 0
    assert "stop" not in json.loads(content)


def test_same_shaped_tables_are_described_once(monkeypatch, fake_project):
    cols = [{"name": "date"}, {"name": "revenue"}]
    monkeypatch.setattr(agent, "describe_schema", lambda p: [
        {"table": "site_a", "columns": cols}, {"table": "site_b", "columns": cols},
        {"table": "site_c", "columns": cols}, {"table": "prices", "columns": [{"name": "sku"}]},
    ])
    out = agent._compact_schema(fake_project())
    assert len(out) == 2
    grouped = next(t for t in out if "same_shape_tables" in t)
    assert grouped["same_shape_tables"] == ["site_a", "site_b", "site_c"]
    assert "3 tables share" in grouped["note"]
