from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_identical_calls: int = Field(3, ge=2, le=1000)
    max_oscillating_cycles: int = Field(2, ge=2, le=100)
    window_seconds: float = Field(30, gt=0, le=3600)
    max_usd_per_minute: float = Field(1.0, gt=0)
    max_tokens_per_minute: int = Field(10000, gt=0)
    global_error_tenant_threshold: int = Field(3, ge=3)
    consecutive_error_threshold: int = Field(3, ge=1)
    fail_closed: bool = True


class ModelRoute(BaseModel):
    model: str = Field(min_length=1)
    max_tokens: int = Field(gt=0, le=131072)
    tier: str
    prompt: str | None = None
    fallback_model: str = "gpt-4o-mini"


class ToolParams(BaseModel):
    name: Literal["charge_card", "query_inventory"]
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPRequest(BaseModel):
    jsonrpc: Literal["2.0"]
    id: str | int | None = None
    method: Literal["tools/call"]
    params: ToolParams


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    messages: list[dict[str, Any]] = Field(min_length=1)
    model: str = "controlled-by-flagsmith"
    stream: Literal[False] = False


class ReleaseRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:@-]+$")


class TelemetryEvent(BaseModel):
    id: int
    timestamp: float
    type: str
    agent_id: str
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)
