from pydantic import BaseModel, Field, model_validator

from .breaker import Breaker
from .models import Policy, ReleaseRequest, ToolParams


class ReplayCall(ReleaseRequest):
    at_seconds: float = Field(ge=0, le=86400)
    tool: ToolParams


class ReplayRequest(BaseModel):
    calls: list[ReplayCall] = Field(min_length=1, max_length=1000)
    candidate_policy: Policy

    @model_validator(mode="after")
    def ordered(self):
        if any(a.at_seconds > b.at_seconds for a, b in zip(self.calls, self.calls[1:])):
            raise ValueError("Calls must be ordered by at_seconds")
        return self


def replay(calls, policy):
    now = [0.0]
    breaker = Breaker(lambda: now[0])
    decisions = []
    for index, call in enumerate(calls):
        now[0] = call.at_seconds
        reason = None
        if call.agent_id not in breaker.quarantine:
            reason = breaker.record_tool_call(call.agent_id, call.tool.name, call.tool.arguments, policy)
            if reason:
                breaker.trip(call.agent_id, reason)
        decisions.append(
            {
                "index": index,
                "agent_id": call.agent_id,
                "blocked": call.agent_id in breaker.quarantine,
                "trip_reason": reason,
            }
        )
    return {
        "blocked_calls": sum(x["blocked"] for x in decisions),
        "quarantined_agents": sorted(breaker.quarantine),
        "decisions": decisions,
    }
