import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..models import CompletionRequest, ModelRoute
from .mcp_proxy import identity

router = APIRouter()


def estimate_cost(model, usage):
    # Public list-price estimates per million tokens; usage is never a billing assertion.
    rates = (0.15, 0.60) if "mini" in model else (2.50, 10.0)
    return (usage.get("prompt_tokens", 0) * rates[0] + usage.get("completion_tokens", 0) * rates[1]) / 1e6


@router.post("/v1/chat/completions")
async def completion(payload: CompletionRequest, request: Request):
    agent, tenant = identity(request)
    async with request.app.state.runtime.agent_budget(agent):
        return await route_completion(payload, request, agent, tenant)


async def route_completion(payload, request, agent, tenant):
    rt = request.app.state.runtime
    rt.telemetry.total += 1
    try:
        flags = rt.control.evaluate(agent, tenant)
    except Exception as exc:
        rt.telemetry.emit("CONTROL_ERROR", agent, str(exc))
        return JSONResponse({"error": "Flagsmith control plane unavailable"}, status_code=503)
    policy, route = flags["policy"], flags["route"]
    if not flags["llm_enabled"] or "llm" in rt.breaker.global_disabled:
        rt.telemetry.emit("BLOCKED", agent, "LLM global circuit open")
        return JSONResponse({"error": {"message": "CIRCUIT_OPEN", "type": "circuit_open"}}, status_code=429)
    if rt.breaker.cost_exceeded(agent, policy):
        rt.trip(agent, "cost_velocity")
        if policy.fail_closed:
            rt.telemetry.emit("BLOCKED", agent, "Token / spend velocity cap", estimated_usd=0.001)
            return JSONResponse(
                {"error": {"message": "CIRCUIT_OPEN: spend cap", "type": "circuit_open"}}, status_code=429
            )
    if agent in rt.breaker.quarantine:
        # Protect the interval before segment write-back / refresh completes.
        route = ModelRoute(model=route.fallback_model, max_tokens=min(route.max_tokens, 256), tier="fallback")
    body = payload.model_dump(exclude_none=True)
    body.update(model=route.model, max_tokens=route.max_tokens)
    if route.prompt:
        body["messages"] = [{"role": "system", "content": route.prompt}, *body["messages"]]
    headers = (
        {"Authorization": f"Bearer {rt.settings.upstream_llm_api_key}"}
        if rt.settings.upstream_llm_api_key
        else {}
    )
    try:
        response = await rt.http.post(rt.settings.upstream_llm_url, json=body, headers=headers)
        if response.status_code >= 500 and route.tier != "fallback":
            rt.record_result(agent, tenant, "llm", False, policy)
            body.update(model=route.fallback_model, max_tokens=min(route.max_tokens, 256))
            route = ModelRoute(model=body["model"], max_tokens=body["max_tokens"], tier="fallback")
            response = await rt.http.post(rt.settings.upstream_llm_url, json=body, headers=headers)
        result = response.json()
    except (httpx.HTTPError, ValueError):
        rt.record_result(agent, tenant, "llm", False, policy)
        return JSONResponse({"error": "LLM upstream unavailable"}, status_code=502)
    rt.record_result(agent, tenant, "llm", response.is_success, policy)
    if response.is_success:
        usage = result.get("usage", {})
        usd = estimate_cost(route.model, usage)
        rt.breaker.record_spend(agent, usage.get("total_tokens", 0), usd)
        if rt.breaker.cost_exceeded(agent, policy):
            rt.trip(agent, "cost_velocity")
        rt.telemetry.emit(
            "LLM_ROUTED",
            agent,
            f"{route.model} / {route.tier}",
            model=route.model,
            tier=route.tier,
            tokens=usage.get("total_tokens", 0),
            usd=usd,
        )
    else:
        rt.telemetry.emit("UPSTREAM_ERROR", agent, f"LLM HTTP {response.status_code}")
    return JSONResponse(
        result,
        status_code=response.status_code,
        headers={
            "X-AgentBreaker-Model": route.model,
            "X-AgentBreaker-Tier": route.tier,
            "X-AgentBreaker-Eval-Ms": f"{rt.control.eval_times[-1]:.4f}",
        },
    )
