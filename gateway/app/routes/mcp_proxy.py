import re
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..models import MCPRequest

router = APIRouter()


def identity(request):
    agent = request.headers.get("X-Agent-Id", "anonymous-agent")
    tenant = request.headers.get("X-Tenant-Id", "default-tenant")
    if not all(re.fullmatch(r"[A-Za-z0-9_.:@-]{1,128}", x) for x in (agent, tenant)):
        raise HTTPException(400, "Agent and tenant IDs must use 1-128 safe identifier characters")
    return agent, tenant


def block(runtime, request_id, agent, tool):
    quarantined = agent in runtime.breaker.quarantine
    runtime.telemetry.emit("BLOCKED", agent, f"CIRCUIT_OPEN {tool}", tool=tool)
    return JSONResponse(
        status_code=429,
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32001,
                "message": "AgentBreaker CIRCUIT_OPEN: tool blocked by Flagsmith policy",
                "data": {"agent_id": agent, "tool": tool, "quarantined": quarantined},
            },
        },
    )


@router.post("/mcp")
async def mcp(payload: MCPRequest, request: Request):
    rt = request.app.state.runtime
    agent, tenant = identity(request)
    tool = payload.params.name
    rt.telemetry.total += 1
    if agent in rt.breaker.quarantine or tool in rt.breaker.global_disabled:
        return block(rt, payload.id, agent, tool)
    try:
        flags = rt.control.evaluate(agent, tenant)
    except Exception as exc:
        rt.telemetry.emit("CONTROL_ERROR", agent, str(exc))
        return JSONResponse({"error": "Flagsmith control plane unavailable"}, status_code=503)
    if not flags[f"mcp_tool_{tool}"]:
        return block(rt, payload.id, agent, tool)
    reason = rt.breaker.record_tool_call(agent, tool, payload.params.arguments, flags["policy"])
    if reason:
        rt.trip(agent, reason)
        return block(rt, payload.id, agent, tool)
    started = time.perf_counter()
    try:
        response = await rt.http.post(rt.settings.upstream_mcp_url, json=payload.model_dump())
        body = response.json()
        success = response.is_success and not body.get("error") and not body.get("result", {}).get("isError")
    except (httpx.HTTPError, ValueError):
        rt.record_result(agent, tenant, tool, False, flags["policy"])
        rt.telemetry.emit("UPSTREAM_ERROR", agent, tool)
        return JSONResponse({"error": "MCP upstream unavailable"}, status_code=502)
    rt.record_result(agent, tenant, tool, success, flags["policy"])
    rt.telemetry.emit(
        "ALLOWED" if success else "UPSTREAM_ERROR",
        agent,
        tool,
        arguments=payload.params.arguments,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
    return JSONResponse(body, status_code=response.status_code)
