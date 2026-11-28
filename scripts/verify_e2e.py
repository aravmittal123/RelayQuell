"""Live-stack assertions. No mocks; reads persisted state directly from Flagsmith."""

import json
import os
import time
import uuid
from contextlib import closing
from pathlib import Path

import httpx
from dotenv import dotenv_values
from flagsmith import Flagsmith

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8085")
FLAGS = os.getenv("FLAGSMITH_PUBLIC_URL", "http://localhost:8000") + "/api/v1/"


def main():
    env = dotenv_values(ROOT / ".env.runtime")
    management = httpx.Client(
        base_url=FLAGS,
        timeout=30,
        headers={"Authorization": "Api-Key " + env["FLAGSMITH_MASTER_API_KEY"]},
    )
    gateway = httpx.Client(base_url=GATEWAY, timeout=30)
    segment_path = (
        f"projects/{env['FLAGSMITH_PROJECT_ID']}/segments/{env['FLAGSMITH_QUARANTINE_SEGMENT_ID']}/"
    )
    results = []

    def check(name, valid):
        assert valid, name
        results.append(name)
        print("PASS: " + name)

    def wait(predicate, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        return False

    def members():
        response = management.get(segment_path)
        response.raise_for_status()

        def walk(rules):
            for rule in rules:
                yield from rule.get("conditions", [])
                yield from walk(rule.get("rules", []))

        condition = next(x for x in walk(response.json()["rules"]) if x.get("property") == "agent_id")
        return set(condition["value"].split(",")) - {"__none__"}

    def release(agent):
        response = gateway.post("/api/quarantine/release", json={"agent_id": agent})
        response.raise_for_status()

    def tool(agent, args=None, name="charge_card"):
        return gateway.post(
            "/mcp",
            headers={"X-Agent-Id": agent},
            json={
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": args if args is not None else {"order_id": uuid.uuid4().hex},
                },
            },
        )

    def llm(agent):
        return gateway.post(
            "/v1/chat/completions",
            headers={"X-Agent-Id": agent},
            json={"messages": [{"role": "user", "content": "Report status"}]},
        )

    check(
        "1. Live gateway uses Flagsmith local evaluation",
        wait(
            lambda: (
                gateway.get("/health").status_code == 200
                and gateway.get("/health").json()["flagsmith_local_eval"]
            )
        ),
    )
    for agent in ["agent_healthy", "agent_runaway"]:
        release(agent)
    check("2. Healthy charge_card call allowed", tool("agent_healthy").status_code == 200)
    for _ in range(3):
        trip = tool("agent_runaway", {"order_id": "repeated-order"})
    check(
        "3. Third identical call fails closed with JSON-RPC -32001",
        trip.status_code == 429 and trip.json()["error"]["code"] == -32001,
    )
    check(
        "4. Runaway ID persisted in real Flagsmith segment",
        wait(lambda: "agent_runaway" in members()),
    )
    check(
        "5a. Healthy agent survives isolated quarantine",
        tool("agent_healthy").status_code == 200,
    )
    response = llm("agent_runaway")
    check(
        "5b. Quarantined LLM uses gpt-4o-mini",
        response.status_code == 200 and response.headers["X-AgentBreaker-Model"] == "gpt-4o-mini",
    )
    with closing(
        Flagsmith(
            environment_key=env["FLAGSMITH_SERVER_KEY"],
            api_url=FLAGS,
            enable_local_evaluation=True,
            environment_refresh_interval_seconds=5,
        )
    ) as sdk:
        flags = sdk.get_identity_flags(
            "agent_runaway",
            traits={"agent_id": "agent_runaway", "tenant_id": "default-tenant"},
        )
        check(
            "5c. Official SDK independently resolves persisted segment override",
            not flags.is_feature_enabled("mcp_tool_charge_card")
            and json.loads(flags.get_feature_value("llm_model_route"))["model"] == "gpt-4o-mini",
        )
    release("agent_runaway")
    check(
        "6. Release removes persisted ID and restores valid calls",
        "agent_runaway" not in members() and tool("agent_runaway").status_code == 200,
    )
    check(
        "Release restores primary LLM route",
        llm("agent_runaway").headers["X-AgentBreaker-Model"] == "gpt-4o",
    )
    oscillating = "e2e_oscillating"
    release(oscillating)
    for name in ["charge_card", "query_inventory", "charge_card", "query_inventory"]:
        response = tool(oscillating, {}, name)
    check("A-B-A-B oscillation fails closed", response.status_code == 429)
    check("Oscillating agent persists", wait(lambda: oscillating in members()))
    release(oscillating)
    with gateway.stream("GET", "/api/events") as stream:
        check(
            "SSE content type",
            stream.status_code == 200 and "text/event-stream" in stream.headers.get("content-type", ""),
        )
        event = next(line for line in stream.iter_lines() if line.startswith("data:"))
        check(
            "SSE contains structured event IDs and agent attribution",
            {"id", "agent_id", "timestamp", "type"} <= json.loads(event[5:]).keys(),
        )
    path = f"environments/{env['FLAGSMITH_ENV_KEY']}/featurestates/"
    states_response = management.get(path)
    states_response.raise_for_status()
    states = states_response.json()
    states = states["results"] if isinstance(states, dict) else states

    features = management.get(f"projects/{env['FLAGSMITH_PROJECT_ID']}/features/").json()
    features = features["results"] if isinstance(features, dict) else features

    def state(name):
        feature_id = next(x["id"] for x in features if x["name"] == name)
        return next(x for x in states if x["feature"] == feature_id and not x.get("feature_segment"))

    policy_state = state("breaker_policy_config")
    policy_path = f"{path}{policy_state['id']}/"
    saved_policy = policy_state["feature_state_value"]
    try:
        original_policy = json.loads(saved_policy)
        original_policy["max_tokens_per_minute"] = 80
        response = management.patch(
            policy_path,
            json={"feature_state_value": json.dumps(original_policy)},
        )
        response.raise_for_status()
        gateway.post("/api/policy/refresh").raise_for_status()
        release("e2e_cost")
        check(
            "Live remote policy refresh changes token cap",
            gateway.get("/health").json()["active_policy"]["max_tokens_per_minute"] == 80,
        )
        check(
            "Budget crossing completion returns before further calls are blocked",
            llm("e2e_cost").status_code == 200 and llm("e2e_cost").status_code == 429,
        )
        check("Cost quarantine persists", wait(lambda: "e2e_cost" in members()))
        if env.get("FLAGSMITH_HEALTH_WEBHOOK_URL"):
            health_path = f"projects/{env['FLAGSMITH_PROJECT_ID']}/feature-health/events/"
            check(
                "Feature Health persists unhealthy webhook incident",
                wait(
                    lambda: any(
                        x["type"] == "UNHEALTHY" and "e2e_cost" in json.dumps(x.get("reason"))
                        for x in management.get(health_path).json()
                    )
                ),
            )
        else:
            check(
                "OSS fallback persists unhealthy incident metadata",
                wait(lambda: "unhealthy" in (management.get(segment_path).json().get("description") or "")),
            )
        original_policy["fail_closed"] = False
        management.patch(
            policy_path, json={"feature_state_value": json.dumps(original_policy)}
        ).raise_for_status()
        gateway.post("/api/policy/refresh").raise_for_status()
        downgraded = llm("e2e_cost")
        check(
            "Non-blocking spend policy downgrades instead of blocking",
            downgraded.status_code == 200 and downgraded.headers["X-AgentBreaker-Tier"] == "fallback",
        )
        release("e2e_cost")
    finally:
        management.patch(policy_path, json={"feature_state_value": saved_policy}).raise_for_status()
        gateway.post("/api/policy/refresh").raise_for_status()
    inventory = state("mcp_tool_query_inventory")
    inventory_path = f"{path}{inventory['id']}/"
    try:
        for i in range(3):
            agent = f"e2e_error_{i}"
            release(agent)
            response = tool(agent, {"simulate_error": True, "nonce": i}, "query_inventory")
            check(f"Distinct upstream error {i + 1} observed", response.status_code == 503)
        check(
            "Global kill persists only after three distinct failing agents",
            wait(lambda: management.get(inventory_path).json()["enabled"] is False),
        )
        check(
            "Global inventory kill blocks a fresh healthy agent",
            tool("e2e_unaffected", {}, "query_inventory").status_code == 429,
        )
        check(
            "Global inventory kill does not disable charge_card",
            tool("agent_healthy").status_code == 200,
        )
    finally:
        management.patch(inventory_path, json={"enabled": inventory["enabled"]}).raise_for_status()
        gateway.post("/api/policy/refresh").raise_for_status()
        for i in range(3):
            release(f"e2e_error_{i}")
    check(
        "Inventory restored after global kill verification",
        tool("e2e_unaffected", {"nonce": uuid.uuid4().hex}, "query_inventory").status_code == 200,
    )
    preview_members = members()
    trace = [
        {"agent_id": "preview-only", "at_seconds": i, "tool": {"name": "charge_card", "arguments": {}}}
        for i in range(3)
    ]
    rehearsal = gateway.post(
        "/api/policy/preview", json={"calls": trace, "candidate_policy": {"max_identical_calls": 4}}
    )
    check(
        "Policy rehearsal compares live and candidate loop decisions without persistence",
        rehearsal.status_code == 200
        and rehearsal.json()["changed_decisions"] == 1
        and members() == preview_members,
    )
    incident_index = gateway.get("/api/incidents")
    check(
        "Incident index excludes tool arguments and explicitly declares memory retention",
        incident_index.status_code == 200
        and not incident_index.json()["durable"]
        and all(set(e) == {"id", "timestamp", "type", "agent_id"} for e in incident_index.json()["events"]),
    )
    samples = []
    with closing(
        Flagsmith(
            environment_key=env["FLAGSMITH_SERVER_KEY"],
            api_url=FLAGS,
            enable_local_evaluation=True,
            environment_refresh_interval_seconds=5,
        )
    ) as sdk:
        for i in range(1000):
            start = time.perf_counter_ns()
            evaluated = sdk.get_identity_flags(
                f"benchmark_{i}",
                traits={"agent_id": f"benchmark_{i}", "tenant_id": "benchmark"},
            )
            for name in ["mcp_tool_charge_card", "mcp_tool_query_inventory", "llm_model_route"]:
                evaluated.is_feature_enabled(name)
            json.loads(evaluated.get_feature_value("llm_model_route"))
            json.loads(evaluated.get_feature_value("breaker_policy_config"))
            samples.append((time.perf_counter_ns() - start) / 1e6)
    samples.sort()
    latency = {
        "mean_ms": sum(samples) / len(samples),
        "p95_ms": samples[949],
        "p99_ms": samples[989],
    }
    check(
        "Local evaluation p95 below one millisecond (1000 samples)",
        latency["p95_ms"] < 1,
    )
    port = os.getenv("DASHBOARD_PORT", dotenv_values(ROOT / ".env").get("DASHBOARD_PORT", "3000"))
    dashboard = httpx.get(f"http://localhost:{port}", timeout=30)
    check("AgentBreaker dashboard responds", dashboard.status_code == 200 and "Vaeltrixis" in dashboard.text)
    (ROOT / "evidence" / "e2e-results.json").write_text(
        json.dumps(
            {
                "passed": len(results),
                "checks": results,
                "local_evaluation": latency,
                "timestamp": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n{len(results)} live assertions passed. Local eval: {latency}")
    gateway.close()
    management.close()


if __name__ == "__main__":
    main()
