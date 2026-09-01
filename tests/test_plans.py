"""The money: estimates, caps, settlement, rollover. A wrong number here is a
wrong invoice, so every branch that decides a credit amount is pinned."""
import pytest
from fastapi import HTTPException

from bizzmind import plans


# ------------------------------------------------------------ conversions

def _marked_up(usd):
    import math
    return max(10, int(math.ceil(usd * plans.CREDITS_PER_USD * plans.SPEND_MARKUP / 10.0) * 10))


@pytest.mark.parametrize("usd", [0.4752, 0.3910, 0.0842, 0.0583, 1.0, 0.001])
def test_credits_are_spend_times_markup_rounded_up_to_ten(usd):
    assert plans.credits_from_usd(usd) == _marked_up(usd)
    assert plans.credits_from_usd(usd) % 10 == 0


def test_the_markup_is_real_and_zero_spend_is_free():
    assert plans.SPEND_MARKUP > 1.0
    assert plans.credits_from_usd(1.0) > plans.CREDITS_PER_USD      # more than at-cost
    assert plans.credits_from_usd(0) == 0
    assert plans.credits_from_usd(None) == 0
    assert plans.credits_from_usd(-1) == 0


def test_one_credit_is_a_fifth_of_a_cent_of_spend():
    assert plans.CREDITS_PER_USD == 500


@pytest.mark.parametrize("charts,cost", [(1, 300), (5, 300), (8, 300), (9, 480), (16, 480), (17, 720), (40, 720)])
def test_deck_estimate_grows_with_the_dashboard(charts, cost):
    assert plans.deck_cost(charts) == cost


def test_deck_prediction_is_not_below_a_measured_run():
    # 8 charts really cost $0.475; a prediction under that would let a run slip
    # past the balance check and the warning
    assert plans.deck_cost(8) >= _marked_up(0.475) * 0.8


def test_presentation_quote_covers_both_halves():
    assert plans.presentation_total(8) == plans.deck_cost(8) + plans.cost_of("presentation") == 380


def test_engine_cost_is_linear_and_never_negative():
    assert plans.engine_cost_usd(39) == pytest.approx(39 * plans.ENGINE_CREDIT_USD)
    assert plans.engine_cost_usd(0) == 0
    assert plans.engine_cost_usd(None) == 0
    assert plans.engine_cost_usd(-5) == 0


def test_analysis_price_scales_by_table_tiers():
    assert plans.cost_of("analysis", "standard", tables=3) == 500
    assert plans.cost_of("analysis", "standard", tables=20) == 800
    assert plans.cost_of("analysis", "standard", tables=45) == 1200
    assert plans.cost_of("analysis", "max", tables=3) == 1200


def test_unknown_model_falls_back_to_standard():
    assert plans.norm_model(None) == "standard"
    assert plans.norm_model("gpt-9") == "standard"
    assert plans.norm_model("max") == "max"


# ------------------------------------------------------------ settle

@pytest.fixture
def org(monkeypatch, fake_pool):
    pool = fake_pool()
    monkeypatch.setattr(plans, "pool", lambda: pool)
    monkeypatch.setattr(plans, "org_of_project", lambda pid: "org-1")
    return pool


def test_settle_charges_marked_up_spend_regardless_of_estimate(org):
    took = plans.settle("p1", "chat", cost_usd=1.0, estimate=200)
    assert took == _marked_up(1.0)                       # the estimate never caps the bill
    assert org.sql_like("UPDATE public.organizations") and org.sql_like("INSERT INTO public.credit_events")
    assert org.log[0][1] == (took, "org-1")


def test_estimate_does_not_change_what_is_billed(org):
    a = plans.settle("p1", "chat", cost_usd=0.5, estimate=10)
    b = plans.settle("p1", "chat", cost_usd=0.5, estimate=0)
    c = plans.settle("p1", "chat", cost_usd=0.5)
    assert a == b == c == _marked_up(0.5)


def test_the_looping_message_would_now_be_billed_in_full(org):
    # the case that motivated the change: $2.71 spent, 50 credits billed
    assert plans.settle("p1", "chat", cost_usd=2.705, estimate=100) == _marked_up(2.705) > 50


def test_settle_of_zero_spend_charges_nothing(org):
    assert plans.settle("p1", "chat", cost_usd=0.0, estimate=200) == 0
    assert plans.settle("p1", "chat", cost_usd=None, estimate=200) == 0
    assert org.log == []


def test_settle_without_an_org_touches_nothing(monkeypatch, fake_pool):
    pool = fake_pool()
    monkeypatch.setattr(plans, "pool", lambda: pool)
    monkeypatch.setattr(plans, "org_of_project", lambda pid: None)
    assert plans.settle("p1", "chat", 1.0, 100) == 0
    assert pool.log == []


def test_settle_records_the_kind_it_was_asked_to_bill(org):
    took = plans.settle("p1", "presentation", 0.0842, 80)
    insert = [p for s, p in org.log if "credit_events" in s][0]
    assert insert == ("org-1", "p1", "presentation", took)


# ------------------------------------------------------------ warnings

def test_expensive_flags_a_big_bite_of_the_balance():
    assert plans.expensive(300, 1000)            # 30% of what is left
    assert plans.expensive(250, 1000)            # exactly the threshold
    assert not plans.expensive(240, 1000)
    assert not plans.expensive(40, 5000)         # a routine question


def test_expensive_is_not_the_same_as_unaffordable():
    assert not plans.expensive(500, 0)           # empty wallet: blocked elsewhere, not "expensive"
    assert plans.expensive(2000, 1000)           # over the balance is also a big bite


# ------------------------------------------------------------ pre-flight

@pytest.fixture
def wallet(monkeypatch):
    state = {"plan": "free", "remaining": 100, "quota": 1000, "extra": 0, "used": 900,
             "auto_recharge": False, "org_name": "x"}
    monkeypatch.setattr(plans, "org_of_project", lambda pid: "org-1")
    monkeypatch.setattr(plans, "org_state", lambda org: state)
    return state


def test_pre_flight_refuses_when_the_whole_action_does_not_fit(wallet):
    with pytest.raises(HTTPException) as e:
        plans.ensure_can_afford("p1", "deck", "bg", need=400)
    assert e.value.status_code == 402
    assert "400" in e.value.detail and "100" in e.value.detail


def test_pre_flight_uses_the_list_price_when_no_override(wallet):
    wallet["remaining"] = 39
    with pytest.raises(HTTPException):
        plans.ensure_can_afford("p1", "chat", "bg")          # chat = 40
    wallet["remaining"] = 40
    plans.ensure_can_afford("p1", "chat", "bg")              # exactly enough passes


def test_max_model_is_locked_on_the_free_plan(wallet):
    wallet["remaining"] = 10_000
    with pytest.raises(HTTPException) as e:
        plans.ensure_can_afford("p1", "chat", "bg", model="max")
    assert e.value.status_code == 403
    wallet["plan"] = "pro"
    plans.ensure_can_afford("p1", "chat", "bg", model="max")


def test_pre_flight_is_a_no_op_for_projects_without_an_org(monkeypatch):
    monkeypatch.setattr(plans, "org_of_project", lambda pid: None)
    plans.ensure_can_afford("p1", "deck", "bg", need=10**9)


# ------------------------------------------------------------ rollover

def _renew(fake_pool, row):
    pool = fake_pool(lambda sql, p: ([row], 0) if sql.startswith("SELECT plan") and row else ([], 0))
    plans._renew_if_due(pool.conn, "org-1")
    return [p for s, p in pool.log if s.startswith("UPDATE")]


def test_rollover_carries_unused_credits_capped_at_twice_monthly(fake_pool):
    ups = _renew(fake_pool, ("pro", 4000, 1000, None))       # 3000 unused + 4000
    assert ups == [(7000, "org-1")]
    ups = _renew(fake_pool, ("pro", 8000, 0, None))          # would be 12000 -> cap 8000
    assert ups == [(8000, "org-1")]
    ups = _renew(fake_pool, ("ultra", 20000, 25000, None))   # overspent: max(0, -5000) + 20000
    assert ups == [(20000, "org-1")]


def test_rollover_skips_one_off_plans_and_orgs_not_due(fake_pool):
    assert _renew(fake_pool, ("free", 1000, 200, None)) == []
    assert _renew(fake_pool, None) == []


def test_org_state_clamps_negative_balances_and_unknown_plans(monkeypatch, fake_pool):
    pool = fake_pool(lambda sql, p: ([("legacy", 100, 0, 500, False, "Acme")], 0)
                     if "credits_extra" in sql else ([], 0))
    monkeypatch.setattr(plans, "pool", lambda: pool)
    st = plans.org_state("org-1")
    assert st["plan"] == "free" and st["remaining"] == 0 and st["org_name"] == "Acme"
