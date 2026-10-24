"""Unit tests for the supervisor and guardrails. Run with: python -m pytest tests -q
(scripts/smoke_test.py covers the full server end to end.)"""
from dialup.agent import guardrails
from dialup.agent.guards import Guard
from dialup.agent.runner import _classify, _is_yes


def guard(budget=0.50):
    return Guard(max_steps=25, max_seconds=900, token_budget=10_000_000, cost_budget=budget)


def test_budget_stops_before_crossing():
    g = guard()
    for _ in range(8):                    # 8 calls at $0.05 = $0.40 spent
        g.record_usage(20_000, 1_000)     # 20k in at $2/M + 1k out at $10/M = $0.05
    v = g.check()                         # next call + closing message would hit $0.50
    assert v.action == "stop" and "budget" in v.reason


def test_budget_leaves_room_when_there_is_room():
    g = guard()
    for _ in range(6):                    # $0.30 spent, $0.40 projected
        g.record_usage(20_000, 1_000)
    assert g.check().action == "ok"


def test_budget_uses_latest_call_when_calls_get_pricier():
    g = guard()
    for _ in range(5):
        g.record_usage(2_000, 100)        # cheap early calls
    g.record_usage(100_000, 1_000)        # one big call ($0.21): average would underestimate
    assert g.check().action == "stop"


def test_budget_zero_means_off():
    g = guard(budget=0)
    g.record_usage(1_000_000, 100_000)
    assert g.check().action == "ok"


def test_irreversible_clicks():
    for text in ["Hold seat 3", "Confirm hold", "Book now", "Pay $19", "Checkout", "立即预订"]:
        assert guardrails.is_irreversible(text), text
    for text in ["Search", "Next page", "Holdings report", "See details"]:
        assert not guardrails.is_irreversible(text), text


def test_secrets_are_never_typed():
    assert guardrails.check_value("Password", "hunter2")
    assert guardrails.check_value("密码", "123456")
    assert guardrails.check_value("Card", "4111 1111 1111 1111")
    assert guardrails.check_value("SSN", "123-45-6789")
    assert guardrails.check_value("From", "San Diego") is None
    assert guardrails.check_value("Phone", "619-233-3004") is None


def test_yes_no_parsing():
    for a in ["yes", "Yeah go ahead", "ok", "1", "是", "好的", "可以"]:
        assert _is_yes(a), a
    for a in ["no", "no, don't", "cancel it", "不要", "不是", "", "Kanwar", "2"]:
        assert not _is_yes(a), a


def test_confirm_has_three_outcomes():
    for a in ["没问题", "行", "嗯，订吧", "sure, go for it", "sounds good", "1", " 1 "]:
        assert _classify(a) == "yes", a
    for a in ["no", "算了", "2", "nope, cancel", "不用了", "never mind"]:
        assert _classify(a) == "no", a
    for a in ["Kanwar", "what time is it?", "um", ""]:
        assert _classify(a) == "unclear", a
