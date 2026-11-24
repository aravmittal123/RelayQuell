# RelayQuell verification

## RelayQuell revision: 24 November 2026

25 Python tests and 29 live Docker assertions passed. New isolated policy rehearsal and argument-free incident index were checked through HTTP against the real stack; rehearsal preserves live segment membership. Browser verification confirmed the redesigned homepage, console navigation, and the actual policy comparison result. Host TypeScript validation and both host/Docker production builds passed. All six containers are healthy. SDK evaluation measured mean 0.066 ms / p95 0.114 ms / p99 0.358 ms over 1,000 evaluations. The repository is now `aravmittal123/RelayQuell`; legacy operational identifiers remain compatible. New screenshot: `evidence/relayquell-home.jpg`.

## Reverification: 24 November 2026

22 Python tests and 27 live assertions passed after a full stack restart. Fixed environment overrides that were not reaching Compose, frontend build-time gateway URL wiring, and persistent Flagsmith signing-key configuration. The signing-key fix prevents regenerated signatures from invalidating Feature Health URLs on restart. A new idempotency test verifies that configuration preserves existing settings and signing material. Measured local evaluation mean 0.202 ms, p95 0.610 ms, p99 2.026 ms. The earlier report below remains historical; production authentication and general MCP transport remain outside the implemented release.

Verified locally on **23 November 2026**, using real self-hosted Flagsmith and PostgreSQL in Docker. No paid provider keys were used.

## Static checks and unit / route tests

| Check | Result |
| --- | --- |
| Ruff: gateway, scripts, demo | Passed |
| Pytest | **21 passed**: 7 breaker, 4 control-plane, 10 route / integration tests |
| Clean npm install | Passed on host and in the Docker build |
| `npx tsc --noEmit` | Passed |
| Next.js 15 production build | Passed on Windows and in Docker |
| npm audit after compatible PostCSS override | **0 vulnerabilities** |

The Python test runner emits one upstream Starlette deprecation warning about its HTTPX TestClient integration. It does not affect results. Host Python: 3.14.6; gateway containers and CI use Python 3.13. Node: 22; Next.js: 15.5.29; Flagsmith SDK: 6.7.0.

## Live end-to-end checks

**27 assertions passed** against the running Docker stack:

* All six requested assertions: healthy local-evaluation health, allowed healthy calls, third identical-call quarantine, direct persisted segment membership, healthy-agent isolation plus fallback LLM routing, and persisted release followed by successful calls.
* Independent official SDK evaluation of the persisted quarantine override, proving that the cheap route comes from Flagsmith.
* Restoration of the primary model after release.
* A-B-A-B oscillation detection and persistence.
* Correct SSE content type and structured event delivery.
* Live policy update to an 80-token rolling cap, subsequent blocking, and persisted cost quarantine.
* Live `fail_closed:false` policy update selecting a cheap fallback completion instead of blocking over-budget LLM traffic; tools remain quarantined.
* A persisted Feature Health `UNHEALTHY` event delivered through the actual Webhook provider.
* Three distinct agents' upstream failures, persisted global inventory kill, healthy inventory blocking, continued healthy payment traffic, and restoration of inventory service.
* Dashboard HTTP response and identity validation.
* Local evaluation p95 below one millisecond over 1,000 distinct identities, including boolean flag resolution and JSON remote-config retrieval and parsing.

| Local evaluation statistic | Measured |
| --- | --- |
| Mean | 0.407 ms |
| p95 | **0.620 ms** |
| p99 | 6.024 ms |

These are the final run's measurements while a clean dashboard install was running concurrently, not a guarantee on other hardware. The preceding idle run measured 0.079 ms mean / 0.190 ms p95 / 0.435 ms p99. CPU scheduling can produce longer tails. The gateway's dashboard also measures its own evaluation path, including Pydantic policy/model validation.

`python scripts/verify_e2e.py` reproduces the checks. Its raw results and the inspected OpenAPI schema are in ignored `evidence/`. The verifier restores temporary policy and global-switch changes. The concurrent demo was then run successfully: the healthy agent completed all six tool calls using the primary model, while the runaway agent's third and later repeated calls returned HTTP 429 / JSON-RPC -32001 and its LLM calls used `gpt-4o-mini`.

## Docker deployment

| Service | Final health | Local address |
| --- | --- | --- |
| postgres | Healthy | Internal only |
| flagsmith | Healthy | http://localhost:8000 |
| mock-mcp | Healthy | Internal only |
| mock-llm | Healthy | Internal only |
| gateway | Healthy | http://localhost:8085 |
| dashboard | Healthy | **http://localhost:3001** |

This machine already had Carriere Roofing running on port 3000. Its services were preserved; ignored `.env` sets `DASHBOARD_PORT=3001` for AgentBreaker. The distributable Compose default remains 3000.

Verified Flagsmith image:

```text
flagsmith/flagsmith@sha256:48905c664152d8ae2c843ec9cee72ff197e7caff6e91b959bb851a235915ea35
```

## Verified Flagsmith API paths

All paths below are relative to `/api/v1/`; placeholders avoid publishing credentials.

| Method | Path | Verified operation |
| --- | --- | --- |
| GET | `/health` (outside API prefix) | Readiness |
| GET | `docs/`, `swagger.json` | Live endpoint/schema inspection |
| POST | `auth/users/` | Registration attempted; exact demo password rejected by similarity validator |
| POST | `auth/login/` | Successful admin authentication after local account provisioning |
| GET, POST | `organisations/` | Organisation reuse / creation |
| GET, POST | `projects/` | Project reuse / creation |
| GET | `projects/{project_id}/` | Saved master-key validity |
| GET | `projects/{project_id}/environments/` | Environment discovery |
| POST | `environments/` | Production creation |
| GET, POST | `organisations/{org_id}/master-api-keys/` | Master key creation |
| GET, POST | `environments/{environment_key}/api-keys/` | Server key creation / reuse |
| GET, POST | `projects/{project_id}/features/` | Four real flags, including multivariate option |
| GET, POST | `projects/{project_id}/segments/` | Quarantine segment creation / reuse |
| GET, PATCH | `projects/{project_id}/segments/{segment_id}/` | Persisted membership merge, release, incident metadata fallback |
| GET | `features/feature-segments/?environment={id}&feature={id}` | Idempotent override discovery |
| POST | `environments/{environment_key}/features/{feature_id}/create-segment-override/` | Tool and model overrides |
| GET | `environment-document/` | Server-key authenticated SDK polling and forced refresh |
| GET | `environments/{environment_key}/featurestates/` | Live policy / switch state reads, name filtering |
| GET, PATCH | `environments/{environment_key}/featurestates/{id}/` | Live policy updates, global kill and recovery |
| GET, POST | `projects/{project_id}/feature-health/providers/` | Real OSS Webhook provider creation / reuse |
| POST | `feature-health/{provider_path}` | Actual unhealthy event delivery |
| GET | `projects/{project_id}/feature-health/events/` | Confirmed persisted UNHEALTHY incident |

The current image exposes feature IDs in environment-state responses. Its policy-update endpoint accepts scalar `feature_state_value` strings, while the segment-override creation endpoint accepts a typed nested value object. Both formats were verified live rather than inferred from a single serializer schema.

Bootstrap was run repeatedly and retained organisation=1, project=1, environment=1, segment=1 without duplicate resources or resetting live controls. Because the specified demo password resembles the specified email, current Django validation rejects REST registration; the script documents and performs the minimal local account provisioning through `manage.py shell`, then uses the APIs for all control-plane setup.

## Browser verification

Healthy Call, Trigger Doom-Loop, Release Quarantine, and Refresh Policy were exercised successfully through the actual dashboard. The UI showed live primary/fallback routing, `CIRCUIT OPEN`, a synced quarantine entry, and successful release. Both the regular viewport and a 390-pixel mobile breakpoint were inspected. The default viewport was restored afterward. A screenshot is saved at `evidence/dashboard-verified.jpg`.

## Scope and remaining limits

The requested local application is built and running. GitHub-hosted CI execution, public hosting, hackathon submission, paid OpenAI/Ollama calls, and the separately suggested video were not performed. The gateway deliberately runs one worker: behavior windows and telemetry are process-local. Admin controls are suitable for this loopback-only demo; remote deployment needs authentication and shared state for replicas.
