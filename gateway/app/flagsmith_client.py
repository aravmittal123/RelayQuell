import asyncio
import copy
import json
import logging
import time
from collections import deque

import httpx
from flagsmith import Flagsmith

from .models import ModelRoute, Policy

log = logging.getLogger(__name__)


class ObservedFlagsmith(Flagsmith):
    last_refresh: float = 0

    def update_environment(self):
        previous = self._local_evaluation
        super().update_environment()
        if self._local_evaluation is not previous:
            self.last_refresh = time.time()


def conditions(rules):
    for rule in rules:
        yield from rule.get("conditions", [])
        yield from conditions(rule.get("rules", []))


class ControlPlane:
    def __init__(self, settings, http):
        self.settings, self.http = settings, http
        self.sdk = None
        self.eval_times = deque(maxlen=1000)
        self.last_error = None

    async def start(self):
        self.sdk = await asyncio.to_thread(
            ObservedFlagsmith,
            environment_key=self.settings.flagsmith_server_key,
            api_url=self.settings.flagsmith_api_url,
            enable_local_evaluation=True,
            environment_refresh_interval_seconds=5,
            request_timeout_seconds=3,
        )
        self.evaluate("startup", "system")

    @property
    def ready(self):
        return bool(
            self.sdk
            and self.sdk._local_evaluation
            and time.time() - self.sdk.last_refresh < self.settings.max_document_age_seconds
        )

    def evaluate(self, agent, tenant):
        if not self.ready:
            raise RuntimeError("Flagsmith local environment document unavailable or stale")
        start = time.perf_counter_ns()
        flags = self.sdk.get_identity_flags(identifier=agent, traits={"agent_id": agent, "tenant_id": tenant})
        policy = Policy.model_validate_json(flags.get_feature_value("breaker_policy_config"))
        route = ModelRoute.model_validate_json(flags.get_feature_value("llm_model_route"))
        result = {
            "mcp_tool_charge_card": flags.is_feature_enabled("mcp_tool_charge_card"),
            "mcp_tool_query_inventory": flags.is_feature_enabled("mcp_tool_query_inventory"),
            "llm_enabled": flags.is_feature_enabled("llm_model_route"),
            "route": route,
            "policy": policy,
        }
        self.eval_times.append((time.perf_counter_ns() - start) / 1_000_000)
        return result

    async def refresh(self):
        previous = self.sdk.last_refresh
        await asyncio.to_thread(self.sdk.update_environment)
        if self.sdk.last_refresh <= previous or not self.ready:
            raise RuntimeError("Environment document refresh failed")

    async def request(self, method, path, **kwargs):
        response = await self.http.request(
            method,
            self.settings.flagsmith_api_url.rstrip("/") + "/" + path.lstrip("/"),
            headers={"Authorization": f"Api-Key {self.settings.flagsmith_master_api_key}"},
            **kwargs,
        )
        response.raise_for_status()
        return response.json() if response.content else None

    @property
    def segment_path(self):
        return (
            f"projects/{self.settings.flagsmith_project_id}/segments/"
            f"{self.settings.flagsmith_quarantine_segment_id}/"
        )

    async def members(self):
        segment = await self.request("GET", self.segment_path)
        condition = next(c for c in conditions(segment["rules"]) if c.get("property") == "agent_id")
        return {x for x in condition["value"].split(",") if x and x != "__none__"}

    async def quarantine(self, agent, enabled):
        segment = await self.request("GET", self.segment_path)
        rules = copy.deepcopy(segment["rules"])
        condition = next(c for c in conditions(rules) if c.get("property") == "agent_id")
        members = {x for x in condition["value"].split(",") if x and x != "__none__"}
        if enabled:
            members.add(agent)
        else:
            members.discard(agent)
        condition["value"] = ",".join(sorted(members)) or "__none__"
        await self.request("PATCH", self.segment_path, json={"rules": rules})
        await self.refresh()

    async def kill(self, resource):
        name = "llm_model_route" if resource == "llm" else f"mcp_tool_{resource}"
        path = f"environments/{self.settings.flagsmith_env_key}/featurestates/"
        states = await self.request("GET", path, params={"feature_name": name})
        if isinstance(states, dict):
            states = states["results"]
        state = next(x for x in states if not x.get("feature_segment"))
        await self.request("PATCH", f"{path}{state['id']}/", json={"enabled": False})
        await self.refresh()

    async def incident(self, agent, reason):
        event = {
            "status": "unhealthy",
            "feature": "mcp_tool_charge_card",
            "environment": "Production",
            "reason": {"text_blocks": [{"text": f"Agent {agent}: {reason}"}], "url_blocks": []},
        }
        if self.settings.flagsmith_health_webhook_url:
            try:
                response = await self.http.post(self.settings.flagsmith_health_webhook_url, json=event)
                response.raise_for_status()
                return
            except httpx.HTTPError:
                log.warning("Feature Health unavailable; persisting incident in segment description")
        await self.request(
            "PATCH", self.segment_path, json={"description": "AgentBreaker incident: " + json.dumps(event)}
        )
