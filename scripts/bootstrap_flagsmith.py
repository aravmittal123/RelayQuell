"""Provision only this demo's resources, using the schema served by its live Flagsmith."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
PUBLIC = os.getenv("FLAGSMITH_PUBLIC_URL", "http://localhost:8000").rstrip("/")
PRIMARY = json.dumps({"model": "gpt-4o", "max_tokens": 1024, "tier": "primary"}, separators=(",", ":"))
FALLBACK = json.dumps(
    {"model": "gpt-4o-mini", "max_tokens": 256, "tier": "fallback"},
    separators=(",", ":"),
)
POLICY = json.dumps(
    {
        "max_identical_calls": 3,
        "max_oscillating_cycles": 2,
        "window_seconds": 30,
        "max_usd_per_minute": 1.0,
        "global_error_tenant_threshold": 3,
        "fail_closed": True,
    }
)


class Bootstrap:
    def __init__(self):
        self.client = httpx.Client(base_url=PUBLIC + "/api/v1/", timeout=60)
        self.endpoints = set()

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        if not response.is_success:
            # Responses may contain generated keys; never print their bodies.
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
        self.endpoints.add(f"{method} /api/v1/{path.split('?')[0]}")
        return response.json() if response.content else None

    def list(self, path, **kwargs):
        items = []
        while path:
            page = self.request("GET", path, **kwargs)
            kwargs = {}
            if isinstance(page, list):
                return items + page
            items.extend(page["results"])
            path = page.get("next")
        return items

    def ensure(self, path, name, body):
        existing = next((x for x in self.list(path) if x.get("name") == name), None)
        return existing or self.request("POST", path, json={"name": name, **body})

    def schema(self):
        for _ in range(120):
            try:
                if httpx.get(PUBLIC + "/health", timeout=3).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Flagsmith did not become healthy within 240 seconds")
        # The docs HTML advertises swagger.json on the unified OSS image.
        schema = self.request("GET", "swagger.json")
        expected = {
            "CustomUserCreate": {"email", "password", "first_name", "last_name"},
            "ListFeature": {
                "name",
                "default_enabled",
                "initial_value",
                "multivariate_options",
            },
            "CustomCreateSegmentOverrideFeatureState": {
                "feature_segment",
                "feature_state_value",
                "enabled",
            },
            "EnvironmentAPIKey": {"name", "key"},
            "MasterAPIKey": {"name", "key"},
            "Segment": {"rules", "name"},
        }
        for name, fields in expected.items():
            actual = schema["components"]["schemas"][name]["properties"]
            if not fields <= actual.keys():
                raise RuntimeError(f"Live Flagsmith schema changed: {name}")
        evidence = ROOT / "evidence"
        evidence.mkdir(exist_ok=True)
        (evidence / "flagsmith-openapi.json").write_text(json.dumps(schema), encoding="utf-8")
        return schema

    def run(self):
        self.schema()
        credentials = {
            "email": os.getenv("FLAGSMITH_ADMIN_EMAIL", "admin@agentbreaker.local"),
            "password": os.getenv("FLAGSMITH_ADMIN_PASSWORD", "AgentBreakerDemo123!"),
        }
        login = self.client.post("auth/login/", json=credentials)
        if login.status_code == 400:
            registered = self.client.post(
                "auth/users/",
                json={
                    **credentials,
                    "first_name": "Local",
                    "last_name": "Admin",
                    "superuser": True,
                },
            )
            if registered.status_code == 400:
                # The mandated demo password resembles the mandated email. Django rejects it via REST.
                # Only provision the account locally; every control-plane resource still uses the API.
                print(
                    "NOTICE: REST registration rejected the demo credentials. "
                    "Provisioning the local account through Django; password validators remain enabled."
                )
                code = (
                    "from django.contrib.auth import get_user_model\n"
                    f"credentials = {credentials!r}\n"
                    "User = get_user_model()\n"
                    'if not User.objects.filter(email=credentials["email"]).exists():\n'
                    "    User.objects.create_superuser(**credentials, "
                    'first_name="Local", last_name="Admin")\n'
                )
                subprocess.run(
                    [
                        "docker",
                        "compose",
                        "exec",
                        "-T",
                        "flagsmith",
                        "python",
                        "manage.py",
                        "shell",
                    ],
                    input=code,
                    text=True,
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                )
            else:
                registered.raise_for_status()
            login = self.client.post("auth/login/", json=credentials)
        login.raise_for_status()
        token = login.json()["key"]
        self.client.headers["Authorization"] = f"Token {token}"
        org = self.ensure("organisations/", "AgentBreaker Org", {})
        projects = self.list("projects/")
        project = next(
            (
                x
                for x in projects
                if x["name"] == "AgentBreaker Control Plane" and x["organisation"] == org["id"]
            ),
            None,
        )
        project = project or self.request(
            "POST",
            "projects/",
            json={"name": "AgentBreaker Control Plane", "organisation": org["id"]},
        )
        pid = project["id"]
        environments = self.list(f"projects/{pid}/environments/")
        env = next((x for x in environments if x["name"] == "Production"), None)
        env = env or self.request("POST", "environments/", json={"name": "Production", "project": pid})
        env_key = env["api_key"]
        runtime = dotenv_values(ROOT / ".env.runtime")
        master = runtime.get("FLAGSMITH_MASTER_API_KEY")
        if master:
            check = self.client.get(f"projects/{pid}/", headers={"Authorization": f"Api-Key {master}"})
            if check.status_code != 200:
                master = None
        if not master:
            # Master secrets are returned once. Reuse saved secrets; rotate an orphaned named key.
            path = f"organisations/{org['id']}/master-api-keys/"
            for key in self.list(path):
                if key["name"] == "AgentBreaker Gateway" and not key["revoked"]:
                    self.request("PATCH", f"{path}{key['prefix']}/", json={"revoked": True})
            master = self.request("POST", path, json={"name": "AgentBreaker Gateway"})["key"]
        server = self.ensure(
            f"environments/{env_key}/api-keys/",
            "AgentBreaker Local Eval",
            {"active": True},
        )
        features_path = f"projects/{pid}/features/"
        features = {}
        for name, value in [
            ("mcp_tool_charge_card", None),
            ("mcp_tool_query_inventory", None),
            ("llm_model_route", PRIMARY),
            ("breaker_policy_config", POLICY),
        ]:
            body = {
                "default_enabled": True,
                "initial_value": value,
                "type": "MULTIVARIATE" if name == "llm_model_route" else "STANDARD",
            }
            if name == "llm_model_route":
                body["multivariate_options"] = [
                    {
                        "type": "unicode",
                        "string_value": FALLBACK,
                        "default_percentage_allocation": 0,
                    }
                ]
            features[name] = self.ensure(features_path, name, body)
        segment = self.ensure(
            f"projects/{pid}/segments/",
            "agentbreaker_quarantined",
            {
                "rules": [
                    {
                        "type": "ALL",
                        "conditions": [],
                        "rules": [
                            {
                                "type": "ANY",
                                "conditions": [
                                    {
                                        "operator": "IN",
                                        "property": "agent_id",
                                        "value": "__none__",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        )
        for name, enabled, value in [
            ("mcp_tool_charge_card", False, None),
            ("llm_model_route", True, FALLBACK),
        ]:
            fid = features[name]["id"]
            overrides = self.list(
                "features/feature-segments/",
                params={"environment": env["id"], "feature": fid},
            )
            if not any(x["segment"] == segment["id"] for x in overrides):
                self.request(
                    "POST",
                    f"environments/{env_key}/features/{fid}/create-segment-override/",
                    json={
                        "enabled": enabled,
                        "feature_state_value": {
                            "type": "unicode",
                            "string_value": value,
                        },
                        "feature_segment": {"segment": segment["id"], "priority": 0},
                    },
                )
        health_url = runtime.get("FLAGSMITH_HEALTH_WEBHOOK_URL", "")
        try:
            health_path = f"projects/{pid}/feature-health/providers/"
            providers = self.list(health_path)
            provider = next((x for x in providers if x["name"] == "Webhook"), None)
            provider = provider or self.request("POST", health_path, json={"name": "Webhook"})
            health_url = provider["webhook_url"]
            parsed = urlsplit(health_url)
            health_url = "http://flagsmith:8000" + parsed.path
            if parsed.query:
                health_url += "?" + parsed.query
        except (RuntimeError, KeyError):
            print(
                "NOTICE: Feature Health provider unavailable in this OSS build; "
                "incidents persist in the quarantine segment description."
            )
        values = {
            "FLAGSMITH_API_URL": "http://flagsmith:8000/api/v1/",
            "FLAGSMITH_SERVER_KEY": server["key"],
            "FLAGSMITH_MASTER_API_KEY": master,
            "FLAGSMITH_PROJECT_ID": pid,
            "FLAGSMITH_ENV_KEY": env_key,
            "FLAGSMITH_QUARANTINE_SEGMENT_ID": segment["id"],
            "FLAGSMITH_HEALTH_WEBHOOK_URL": health_url,
        }
        runtime_path = ROOT / ".env.runtime"
        temp = runtime_path.with_suffix(".runtime.tmp")
        temp.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
        temp.replace(runtime_path)
        if os.name != "nt":
            runtime_path.chmod(0o600)
        (ROOT / "evidence" / "bootstrap-endpoints.json").write_text(
            json.dumps(sorted(self.endpoints), indent=2), encoding="utf-8"
        )
        print(
            f"Bootstrap complete: project={pid}, environment={env['id']}, segment={segment['id']}. "
            "Secrets saved to ignored .env.runtime."
        )
        self.client.close()


if __name__ == "__main__":
    try:
        Bootstrap().run()
    except Exception as exc:
        print(f"Bootstrap failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
