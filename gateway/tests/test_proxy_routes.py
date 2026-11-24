import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import ModelRoute, Policy


class FakeControl:
    sdk = None
    ready = True
    eval_times = [0.01]

    def __init__(self):
        self.persisted = set()
        self.fail = False
        self.policy = Policy()
        self.killed = set()

    async def start(self):
        pass

    async def members(self):
        return self.persisted

    async def refresh(self):
        pass

    async def quarantine(self, agent, enabled):
        if self.fail:
            raise RuntimeError("offline")
        self.persisted.add(agent) if enabled else self.persisted.discard(agent)

    async def incident(self, agent, reason):
        pass

    async def kill(self, resource):
        self.killed.add(resource)

    def evaluate(self, agent, tenant):
        if self.fail:
            raise RuntimeError("offline")
        return {
            "policy": self.policy,
            "route": ModelRoute(model="gpt-4o", max_tokens=1024, tier="primary"),
            "llm_enabled": True,
            "mcp_tool_charge_card": "charge_card" not in self.killed,
            "mcp_tool_query_inventory": True,
        }


@pytest.fixture
def fixture():
    control = FakeControl()
    requests = []

    async def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        if body.get("simulate_error") or body.get("params", {}).get("arguments", {}).get("simulate_error"):
            return httpx.Response(503, json={"error": "failure"})
        if request.url.path == "/mcp":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        await asyncio.sleep(0.02)
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "choices": [],
                "usage": {"prompt_tokens": 16, "completion_tokens": 64, "total_tokens": 80},
            },
        )

    app = create_app(
        Settings(
            _env_file=None,
        ),
        control=control,
        transport=httpx.MockTransport(handle),
    )
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, control=control, requests=requests, app=app)


def tool(f, agent="a", args=None):
    return f.client.post(
        "/mcp",
        headers={"X-Agent-Id": agent},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "charge_card", "arguments": args or {}},
        },
    )


def llm(f, agent="a", **extra):
    return f.client.post(
        "/v1/chat/completions",
        headers={"X-Agent-Id": agent},
        json={"messages": [{"role": "user", "content": "hello"}], **extra},
    )


def test_trip_blocks_before_forwarding_and_healthy_survives(fixture):
    f = fixture
    assert tool(f).status_code == 200
    assert tool(f).status_code == 200
    response = tool(f)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == -32001
    assert len(f.requests) == 2
    assert tool(f, "healthy").status_code == 200
    assert llm(f).headers["X-AgentBreaker-Model"] == "gpt-4o-mini"


def test_release_resets_detector(fixture):
    f = fixture
    for _ in range(3):
        tool(f)
    assert f.client.post("/api/quarantine/release", json={"agent_id": "a"}).status_code == 200
    assert tool(f).status_code == 200


def test_release_failure_retains_quarantine(fixture):
    f = fixture
    f.app.state.runtime.breaker.trip("a", "loop")
    f.control.fail = True
    assert f.client.post("/api/quarantine/release", json={"agent_id": "a"}).status_code == 503
    assert tool(f).status_code == 429


def test_local_eval_failure_is_fail_closed(fixture):
    fixture.control.fail = True
    assert tool(fixture).status_code == 503
    assert llm(fixture).status_code == 503
    assert not fixture.requests


def test_llm_rewrites_model_and_enforces_cost(fixture):
    f = fixture
    f.control.policy = Policy(max_tokens_per_minute=80)
    response = llm(f, model="ignored")
    assert response.status_code == 200
    assert response.headers["X-AgentBreaker-Tier"] == "primary"
    assert json.loads(f.requests[0].content)["max_tokens"] == 1024
    assert llm(f).status_code == 429


def test_upstream_fallback_and_three_distinct_agent_global_trip(fixture):
    f = fixture
    response = llm(f, simulate_error=True)
    assert response.status_code == 503
    assert response.headers["X-AgentBreaker-Model"] == "gpt-4o-mini"
    for agent in ["a", "b", "c"]:
        assert tool(f, agent, {"simulate_error": True}).status_code == 503
    assert tool(f, "healthy").status_code == 429


def test_validation_and_admin_endpoints(fixture):
    f = fixture
    assert tool(f, "invalid,agent").status_code == 400
    assert llm(f, stream=True).status_code == 422
    assert f.client.post("/mcp", json={}).status_code == 422
    assert f.client.get("/api/state").status_code == 200
    assert f.client.post("/api/policy/refresh").status_code == 200


def test_restart_restores_persisted_quarantine():
    control = FakeControl()
    control.persisted.add("a")
    with TestClient(
        create_app(
            Settings(
                _env_file=None,
            ),
            control=control,
        )
    ) as client:
        response = client.post(
            "/mcp",
            headers={"X-Agent-Id": "a"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "charge_card", "arguments": {}},
            },
        )
        assert response.status_code == 429


def test_concurrent_llm_calls_cannot_bypass_agent_budget(fixture):
    f = fixture
    f.control.policy = Policy(max_tokens_per_minute=80)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: llm(f), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 429]
    assert len(f.requests) == 1
    assert not f.app.state.runtime.agent_locks


def test_non_blocking_budget_policy_downgrades_to_fallback(fixture):
    f = fixture
    f.control.policy = Policy(max_tokens_per_minute=80, fail_closed=False)
    assert llm(f).status_code == 200
    response = llm(f)
    assert response.status_code == 200
    assert response.headers["X-AgentBreaker-Tier"] == "fallback"
    assert tool(f).status_code == 429


def test_policy_preview_has_no_live_side_effects(fixture):
    calls = [
        {"agent_id": "loop", "at_seconds": i, "tool": {"name": "charge_card", "arguments": {}}}
        for i in range(3)
    ]
    result = fixture.client.post(
        "/api/policy/preview", json={"calls": calls, "candidate_policy": {"max_identical_calls": 4}}
    )
    assert result.status_code == 200
    assert result.json()["changed_decisions"] == 1
    assert not fixture.control.persisted
    assert not fixture.requests
    assert fixture.client.get("/api/incidents").json()["events"] == []
