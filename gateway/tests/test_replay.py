import pytest
from pydantic import ValidationError

from app.models import Policy
from app.replay import ReplayRequest, replay


def trace():
    return [
        {"agent_id": agent, "at_seconds": i, "tool": {"name": "charge_card", "arguments": {}}}
        for i, agent in enumerate(["loop", "healthy", "loop", "loop"])
    ]


def test_policy_comparison_preserves_agent_isolation():
    req = ReplayRequest(calls=trace(), candidate_policy=Policy(max_identical_calls=4))
    assert replay(req.calls, Policy())["quarantined_agents"] == ["loop"]
    assert replay(req.calls, req.candidate_policy)["blocked_calls"] == 0


def test_unsorted_trace_rejected():
    with pytest.raises(ValidationError):
        ReplayRequest(calls=list(reversed(trace())), candidate_policy=Policy())
