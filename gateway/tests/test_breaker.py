from app.breaker import Breaker
from app.models import Policy


def test_identical_loop_and_agent_isolation():
    b, p = Breaker(), Policy()
    assert b.record_tool_call("a", "charge_card", {"x": 1}, p) is None
    assert b.record_tool_call("a", "charge_card", {"x": 1}, p) is None
    assert b.record_tool_call("a", "charge_card", {"x": 1}, p) == "identical_tool_loop"
    assert b.record_tool_call("b", "charge_card", {"x": 1}, p) is None


def test_canonical_argument_order():
    b, p = Breaker(), Policy()
    for args in [{"x": 1, "y": 2}, {"y": 2, "x": 1}]:
        assert b.record_tool_call("a", "charge_card", args, p) is None
    assert b.record_tool_call("a", "charge_card", {"x": 1, "y": 2}, p)


def test_oscillation():
    b, p = Breaker(), Policy()
    for tool in ["charge_card", "query_inventory", "charge_card"]:
        assert b.record_tool_call("a", tool, {}, p) is None
    assert b.record_tool_call("a", "query_inventory", {}, p) == "oscillating_tool_loop"


def test_expired_calls_do_not_trip():
    now = [0.0]
    b, p = Breaker(lambda: now[0]), Policy()
    b.record_tool_call("a", "charge_card", {}, p)
    b.record_tool_call("a", "charge_card", {}, p)
    now[0] = 31
    assert b.record_tool_call("a", "charge_card", {}, p) is None


def test_cost_and_token_caps_expire():
    now = [0.0]
    b, p = Breaker(lambda: now[0]), Policy()
    b.record_spend("usd", 1, 1.0)
    b.record_spend("tokens", 10000, 0)
    assert b.cost_exceeded("usd", p)
    assert b.cost_exceeded("tokens", p)
    assert not b.cost_exceeded("healthy", p)
    now[0] = 60
    assert not b.cost_exceeded("usd", p)
    assert not b.cost_exceeded("tokens", p)


def test_error_burst_requires_distinct_agents_and_expires():
    now = [0.0]
    b, p = Breaker(lambda: now[0]), Policy()
    for _ in range(2):
        assert b.record_result("a", "t", "tool", False, p) == (False, False)
    assert b.record_result("a", "t", "tool", False, p) == (True, False)
    assert b.record_result("b", "t", "tool", False, p) == (False, False)
    assert b.record_result("c", "t2", "tool", False, p) == (False, True)
    assert b.record_result("a", "t", "tool", True, p) == (False, False)
    now[0] = 61
    assert b.record_result("d", "t", "tool", False, p) == (False, False)


def test_release_clears_behavior_and_spend():
    b = Breaker()
    b.trip("a", "loop")
    b.record_spend("a", 10000, 1)
    b.release("a")
    assert "a" not in b.quarantine
    assert not b.cost_exceeded("a", Policy())
