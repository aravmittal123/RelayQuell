import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..models import ReleaseRequest
from ..replay import ReplayRequest, replay

router = APIRouter()


@router.post("/api/policy/preview")
def preview(payload: ReplayRequest, request: Request):
    rt = request.app.state.runtime
    try:
        active = rt.control.evaluate("policy-preview", "system")["policy"]
    except Exception as exc:
        raise HTTPException(503, "Active Flagsmith policy unavailable") from exc
    baseline = replay(payload.calls, active)
    candidate = replay(payload.calls, payload.candidate_policy)
    return {
        "mode": "dry_run",
        "scope": "tool-loop detection only",
        "active_policy": active.model_dump(),
        "candidate_policy": payload.candidate_policy.model_dump(),
        "baseline": baseline,
        "candidate": candidate,
        "changed_decisions": sum(
            a["blocked"] != b["blocked"] for a, b in zip(baseline["decisions"], candidate["decisions"])
        ),
    }


@router.get("/api/incidents")
def incidents(request: Request):
    rt = request.app.state.runtime
    kinds = {"TRIPPED", "QUARANTINED", "RELEASED", "GLOBAL_KILL", "SYNC_ERROR"}
    return {
        "retention": "in_memory_last_1000_events",
        "durable": False,
        "events": [
            {k: e[k] for k in ("id", "timestamp", "type", "agent_id")}
            for e in list(rt.telemetry.events)
            if e["type"] in kinds
        ],
    }


@router.get("/health")
def health(request: Request):
    rt = request.app.state.runtime
    try:
        policy = rt.control.evaluate("health", "system")["policy"].model_dump()
    except Exception:
        policy = None
    ready = rt.control.ready and policy is not None
    return JSONResponse(
        {
            "flagsmith_local_eval": ready,
            "last_environment_refresh": rt.control.sdk.last_refresh,
            "active_policy": policy,
        },
        status_code=200 if ready else 503,
    )


@router.get("/api/state")
def state(request: Request):
    rt = request.app.state.runtime
    try:
        flags = rt.control.evaluate("dashboard", "system")
        flags = {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in flags.items()}
    except Exception:
        flags = {}
    latencies = rt.control.eval_times
    return {
        "total_calls": rt.telemetry.total,
        "blocked_calls": rt.telemetry.blocked,
        "estimated_usd_saved": rt.telemetry.saved,
        "avg_eval_ms": sum(latencies) / len(latencies) if latencies else 0,
        "quarantined_agents": rt.breaker.quarantine,
        "flags": flags,
        "flagsmith_connected": rt.control.ready,
        "timestamp": time.time(),
    }


@router.get("/api/events")
async def events(request: Request):
    try:
        after = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        raise HTTPException(400, "Invalid Last-Event-ID") from None
    return StreamingResponse(
        request.app.state.runtime.telemetry.stream(after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/quarantine/release")
async def release(payload: ReleaseRequest, request: Request):
    rt = request.app.state.runtime
    async with rt.lock:
        try:
            await rt.control.quarantine(payload.agent_id, False)
        except Exception as exc:
            raise HTTPException(503, "Release not committed; quarantine retained") from exc
        rt.breaker.release(payload.agent_id)
        rt.telemetry.emit("RELEASED", payload.agent_id, "Flagsmith segment and local quarantine cleared")
    return {"released": payload.agent_id}


@router.post("/api/policy/refresh")
async def refresh(request: Request):
    rt = request.app.state.runtime
    try:
        await rt.control.refresh()
    except Exception as exc:
        raise HTTPException(503, "Flagsmith refresh failed") from exc
    rt.telemetry.emit("POLICY_REFRESHED", "system", "Live environment document refreshed")
    return {"refreshed": True}
