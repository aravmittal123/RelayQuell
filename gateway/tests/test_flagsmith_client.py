import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.config import Settings
from app.flagsmith_client import ControlPlane, conditions


def test_segment_write_and_incident_fallback():
    async def run():
        seen = []
        segment = {
            "rules": [
                {
                    "id": 4,
                    "type": "ALL",
                    "rules": [
                        {
                            "id": 5,
                            "type": "ANY",
                            "conditions": [
                                {"id": 6, "property": "agent_id", "operator": "IN", "value": "existing"}
                            ],
                        }
                    ],
                }
            ]
        }

        def handle(request):
            assert request.headers["Authorization"] == "Api-Key secret"
            seen.append(request)
            if request.method == "PATCH":
                payload = json.loads(request.content)
                if "rules" in payload:
                    segment["rules"] = payload["rules"]
            return httpx.Response(200, json=segment)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            c = ControlPlane(Settings(_env_file=None, flagsmith_master_api_key="secret"), http)
            c.sdk = SimpleNamespace(last_refresh=time.time(), _local_evaluation=True)
            c.sdk.update_environment = lambda: setattr(c.sdk, "last_refresh", time.time() + 1)
            await c.quarantine("new", True)
            assert next(conditions(segment["rules"]))["value"] == "existing,new"
            await c.quarantine("new", False)
            assert next(conditions(segment["rules"]))["value"] == "existing"
            await c.incident("a", "loop")
            assert "unhealthy" in json.loads(seen[-1].content)["description"]
            assert next(conditions(segment["rules"]))["id"] == 6

    asyncio.run(run())


def test_management_failure_is_not_swallowed():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"detail": "denied"}))
        ) as http:
            c = ControlPlane(
                Settings(
                    _env_file=None,
                ),
                http,
            )
            with pytest.raises(httpx.HTTPStatusError):
                await c.quarantine("a", True)

    asyncio.run(run())


def test_stale_sdk_never_falls_back_to_remote_evaluation():
    c = ControlPlane(
        Settings(
            _env_file=None,
        ),
        None,
    )
    c.sdk = SimpleNamespace(last_refresh=0, _local_evaluation=True, get_identity_flags=Mock())
    with pytest.raises(RuntimeError):
        c.evaluate("a", "t")
    c.sdk.get_identity_flags.assert_not_called()


def test_global_kill_targets_only_environment_state():
    async def run():
        seen = []

        def handle(request):
            seen.append(request)
            return httpx.Response(200, json=[{"id": 12, "feature": 1, "feature_segment": None}])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            c = ControlPlane(Settings(_env_file=None, flagsmith_env_key="prod"), http)
            c.sdk = SimpleNamespace(last_refresh=time.time(), _local_evaluation=True)
            c.sdk.update_environment = lambda: setattr(c.sdk, "last_refresh", time.time() + 1)
            await c.kill("charge_card")
            assert seen[0].url.params["feature_name"] == "mcp_tool_charge_card"
            assert seen[-1].url.path.endswith("/featurestates/12/")
            assert json.loads(seen[-1].content) == {"enabled": False}

    asyncio.run(run())
