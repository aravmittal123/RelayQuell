# Toggle Wars — submission draft

Use Track 3 only. Edit the feedback to reflect your own experience before submitting. A public or unlisted video URL is required; upload the final narrated video to YouTube or Loom and paste the actual URL. Do not use localhost as the live deployment URL.

## Project title

Vaeltrixis — Runtime Control for AI Agents

## Tracks

Track 3: Build on Open Source Flagsmith

## Demo video

**Pending:** upload an under-three-minute video to YouTube or Loom, then paste its public or unlisted URL.

## GitHub repository

https://github.com/aravmittal123/Vaeltrixis

## Live demo or deployment

**Pending:** leave this blank until an externally accessible deployment has actually been secured, deployed, and verified. The current Docker demo runs locally.

## What did you build, and what problem does it solve?

Vaeltrixis is a self-hosted runtime gateway for teams operating tool-using AI agents. It detects repeated tool calls, two-step loops, spend velocity and upstream error bursts. When one agent runs away, the gateway immediately quarantines that agent while healthy agents continue. It can route a quarantined agent to a lower-cost model, expose live telemetry, and let an operator release the quarantine. A policy rehearsal endpoint compares a proposed loop threshold with the active policy against a recorded-style trace without executing tools or changing flags.

Developers run the gateway, dashboard and self-hosted Flagsmith with Docker. The repository includes deterministic mock tool and model servers so the control loop can be tested without paid API keys. This is a local prototype with two supported tool schemas and non-streaming completions; it does not yet provide authentication, full MCP transport or shared multi-worker state.

## Which parts of Flagsmith did you use?

Self-hosted Flagsmith is the control plane. We use project feature flags to enable or disable tool calls, JSON remote configuration for breaker policy and model routing, a multivariate model-route option, and an identity segment with overrides for quarantined agents. The official Python SDK evaluates the environment document locally and refreshes it on a five-second interval. The gateway writes quarantine membership and global switches through the Management API, forces a refresh, and sends unhealthy events to a Feature Health webhook when available. A direct API read and independent SDK evaluation in the live test verify that quarantine was actually persisted and applied.

## Track 3: How did you build on self-hosted Flagsmith?

We run the official Flagsmith Docker image with PostgreSQL in Docker Compose. Around it we built a FastAPI tool and model gateway, a Next.js operations console, policy rehearsal, mock upstreams, bootstrap automation and end-to-end verification. The gateway uses Flagsmith flags and identity segments to control requests, rather than treating Flagsmith as a dashboard-only integration.

Another developer can clone the repository, install the Python dependencies and run `make up` followed by `make demo`. The bootstrap script creates the local project, flags, segment and server key; the configuration guide explains how to point supported requests at another upstream. `make test` runs the Python tests and live-stack verification. The repository documents the current security and protocol limits before real deployments.

## Track 1, Track 2 and Track 4

Leave these blank unless you enter those tracks and have actual evidence for their specific requirements. This project does not claim a completed Flagsmith experiment or a measured Track 4 token count.

## Feedback on Flagsmith — edit to reflect your experience

Local evaluation and segment overrides made it possible to keep per-agent decisions close to the gateway while managing policy centrally. The environment document and Management API were useful for testing the complete quarantine and recovery loop. Bootstrap required extra work to understand the live API response shapes and keep webhook signing configuration stable across restarts. Clearer self-hosted bootstrap examples and versioned management API examples for nested segment rules and overrides would make this workflow easier for new developers.
