# Configuration: what you actually need to change

## Local trial

You do not need to fill every field in `.env.example`.

Create `.env` with only your overrides. On this computer use:

```dotenv
DASHBOARD_PORT=3001
```

Run the bootstrap script after starting Flagsmith. It creates the project, flags, keys and quarantine segment, then writes `.env.runtime`. Do not copy blank generated keys or zero IDs into this file. Do not commit either environment file.

Before first startup run `python scripts/configure.py` (also done by `make up`). It generates a stable random `DJANGO_SECRET_KEY` in your ignored `.env`. Preserve this key across restarts: Flagsmith signs webhook URLs with it. Losing or rotating it requires rerunning bootstrap to regenerate provider URLs and recreating the gateway. Never post its value in chat or GitHub.

## Connect an existing system

AgentBreaker sits between your agent and its upstream services. It is for teams running tool-using agents who need per-agent isolation, spending controls and model routing. It is not a model, agent framework, payment processor, or replacement for tool permissions.

Configure your upstream endpoints in `.env`:

```dotenv
UPSTREAM_MCP_URL=http://host.docker.internal:9000/mcp
UPSTREAM_LLM_URL=https://api.openai.com/v1/chat/completions
UPSTREAM_LLM_API_KEY=your-provider-key
```

`host.docker.internal` reaches a service running on the Docker Desktop host. `localhost` inside the gateway container refers to that container, not your computer. On a Linux server use a reachable container/service hostname or configure the host gateway explicitly.

After changing gateway settings:

```sh
docker compose up -d --force-recreate gateway
```

Changing the upstream URL does not make every MCP server compatible. The current interceptor supports JSON-RPC `tools/call` for `charge_card` and `query_inventory`. It does not implement MCP session initialization, streaming transport, or arbitrary tool discovery. Add and test tool schemas and their Flagsmith flags before onboarding other tools.

For OpenAI-compatible clients:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8085/v1",
    api_key="local-client-placeholder",
    default_headers={"X-Agent-Id": "orders-worker-1", "X-Tenant-Id": "warehouse-team"},
)
response = client.chat.completions.create(
    model="controlled-by-flagsmith",
    messages=[{"role": "user", "content": "Summarise today's orders"}],
)
print(response.choices[0].message.content)
```

The placeholder client key is not gateway authentication. The upstream provider key stays in the gateway. Use stable agent IDs, not a new random ID per request. The supplied model and max-token settings are replaced by Flagsmith's route. Streaming is currently unsupported.

For Ollama, set `UPSTREAM_LLM_URL=http://host.docker.internal:11434/v1/chat/completions`, leave the provider key empty, and change both the primary remote config and quarantine override to models installed in Ollama. The default GPT model names will not work with an Ollama installation that lacks those models.

## Settings reference

| Setting | Who configures it? | Purpose |
| --- | --- | --- |
| `DASHBOARD_PORT` | You, if needed | Published local dashboard port |
| `POSTGRES_PASSWORD` | Deployment owner | Database credential; changing it does not change an existing database user's password |
| `FLAGSMITH_ADMIN_EMAIL`, `FLAGSMITH_ADMIN_PASSWORD` | Deployment owner | Initial local Flagsmith account; existing account passwords are not reset |
| `FLAGSMITH_PUBLIC_URL` | You, if needed | Host-side URL used by bootstrap |
| `FLAGSMITH_API_URL` | You, if needed | Gateway-to-Flagsmith URL; normally the Docker service hostname |
| Server/master keys, project/environment/segment IDs | Bootstrap | Resolved automatically into `.env.runtime` |
| `FLAGSMITH_HEALTH_WEBHOOK_URL` | Bootstrap | Secret provider webhook address |
| `UPSTREAM_MCP_URL` | Integration owner | Supported JSON-RPC tool endpoint |
| `UPSTREAM_LLM_URL`, `UPSTREAM_LLM_API_KEY` | Integration owner | Provider's full completion URL and optional secret |
| `CORS_ORIGINS` | Deployment owner | Exact browser origins permitted to call the gateway |
| `MAX_DOCUMENT_AGE_SECONDS` | Deployment owner | Maximum local-document age before requests fail closed |
| `NEXT_PUBLIC_GATEWAY_URL` | Frontend build owner | Browser-visible gateway URL, compiled into the Next.js bundle; runtime container variables alone do not change a built bundle |

## Deployment boundary

This release is a tested local prototype, not a certified production deployment. Before shared or internet-facing use, implement authenticated agent identities and administrator access, TLS, secret rotation, request limits, upstream-specific validation, durable audit records, backup/restore and load/failure testing. Multiple gateway workers require shared atomic breaker state and distributed synchronization. Do not expose the unauthenticated admin API publicly.

Keep the mocks for repeatable integration tests. Production deployments must point to real upstreams and validate their behavior with non-sensitive test traffic. Passing mock tests does not certify a real payment or model-provider integration.
