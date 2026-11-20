"""Measuring an approved policy on the sessions pushed after it was approved (rollup.policy_outcomes)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from server.app.pipeline.rollup import policy_outcomes

APPROVED = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
RULE = "Never skip or mark a failing test as xfail to make the suite pass."


def _session(aid: int, pushed: datetime, decisions: list[NS], rules: list[dict] | None = None, dev: str = "dev-a") -> dict:
    return {
        "analysis": NS(id=aid), "push": NS(received_at=pushed), "dev": dev,
        "steering": {"rules": rules or []}, "decisions": decisions,
    }


def _override(statement: str) -> NS:
    return NS(actor="human", kind="reject", statement=statement, rule_id=None, rule_followed=None)


def _cited(rule_id: str, followed: bool) -> NS:
    return NS(actor="agent", kind="choice", statement="", rule_id=rule_id, rule_followed=followed)


STEER = [{"id": "S4", "text": RULE}]


def test_sessions_before_approval_are_ignored():
    before = APPROVED - timedelta(hours=1)
    data = [_session(1, before, [_override("Never mark a test xfail to make the suite pass; fix it.")])]
    out = policy_outcomes(RULE, APPROVED, data)
    assert out == {"after": None, "adherence": None, "recurrence": None}


def test_no_override_after_approval_gives_zero_not_none():
    after = APPROVED + timedelta(hours=1)
    data = [_session(2, after, [_cited("S4", True)], STEER)]
    out = policy_outcomes(RULE, APPROVED, data)
    assert out["after"] == 0
    assert out["adherence"] == 100
    assert out["recurrence"] is None


def test_repeated_override_after_approval_counts_per_100_sessions():
    after = APPROVED + timedelta(hours=1)
    data = [
        _session(3, after, [_override("Never mark a test xfail to make the suite pass; fix the test.")], STEER, dev="dev-a"),
        _session(4, after, [], STEER, dev="dev-b"),
        _session(5, after, [_cited("S4", False)], STEER, dev="dev-b"),
        _session(6, after, [_cited("S4", True)], STEER, dev="dev-c"),
    ]
    out = policy_outcomes(RULE, APPROVED, data)
    assert out["after"] == 25  # 1 overridden session of 4
    assert out["adherence"] == 50  # 1 of 2 citing decisions followed
    assert out["recurrence"] == {"sessions": 1, "teams": 1, "developers": 1}


def test_a_rule_with_different_text_is_not_counted_as_adherence():
    after = APPROVED + timedelta(hours=1)
    other = [{"id": "S7", "text": "Mark slow or flaky tests with xfail so the CI pipeline stays green."}]
    data = [_session(7, after, [_cited("S7", True)], other)]
    out = policy_outcomes(RULE, APPROVED, data)
    assert out["adherence"] is None
