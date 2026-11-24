# RelayQuell: runtime containment for tool-using agents

## The real problem

An automation can repeat a tool call indefinitely, oscillate between tools, exhaust its token budget, or keep hitting a failing upstream. Operators need to contain the affected identity without shutting down unrelated work. They also need a way to change policy and recover without redeploying application code.

RelayQuell targets platform teams operating internal tool-using agents. A useful first deployment is a trusted, single-gateway automation environment with the two supported tool schemas. Payments must still enforce their own idempotency: a loop detector is not transaction deduplication and cannot reverse calls already executed.

## Different from the existing AgentBreaker

KageX describes its [AgentBreaker](https://kagex.ai/products/agentbreaker) as an AI red-team tool for prompt injection, jailbreaks and data leakage. Its [public repository](https://github.com/kagexai/agentbreaker) describes campaign generation, execution, scoring and reporting. RelayQuell does not reproduce those attack-generation features. It enforces operational containment in the request path, backed by self-hosted Flagsmith. These are complementary categories; no head-to-head performance or security superiority is claimed.

Name check on 24 November 2026: GitHub repository-name search for `RelayQuell` returned zero matches before this repository was renamed. Search availability does not establish trademark rights or domain availability.

## What an operator can do now

1. Route supported tool requests and non-streaming OpenAI-compatible calls through the gateway.
2. Observe a runaway agent trip locally while unrelated agents continue.
3. Inspect the persisted Flagsmith quarantine segment and its model override.
4. Rehearse a chronological tool-call trace against the live loop policy and a candidate policy using `POST /api/policy/preview`.
5. Review a bounded, argument-free session incident index at `GET /api/incidents`.
6. Release an agent after the Flagsmith removal and forced refresh succeed.

Policy replay is tool-loop simulation only: it does not simulate spend, LLM fallback, upstream errors, segment membership or global kill rules. It does not publish the candidate. Make an intentional edit in Flagsmith after reviewing the comparison. Incident records are memory-bound and are not a durable or tamper-evident audit trail.

## Reproduce policy rehearsal

```sh
curl http://localhost:8085/api/policy/preview \
  -H 'Content-Type: application/json' \
  -d '{"candidate_policy":{"max_identical_calls":4},"calls":[
    {"agent_id":"worker-a","at_seconds":0,"tool":{"name":"charge_card","arguments":{"order":"same"}}},
    {"agent_id":"worker-a","at_seconds":1,"tool":{"name":"charge_card","arguments":{"order":"same"}}},
    {"agent_id":"worker-a","at_seconds":2,"tool":{"name":"charge_card","arguments":{"order":"same"}}}
  ]}'
```

With the default active policy, baseline blocks the third call and candidate allows it. Changing the live policy changes the baseline. The preview constructs isolated breaker instances and performs no upstream execution or Flagsmith writes. Input is bounded to 1,000 ordered calls and validated using the same policy schema as live evaluation.

## Track 3 evidence

Flagsmith is authoritative for tool switches, model routes, segment overrides and breaker configuration. Show it running locally, prove the segment write directly, demonstrate zero collateral tool blocking for the healthy agent, then show recovery. The existing live verifier exercises those behaviors against actual Docker services. The two new endpoints have additional isolated tests and live smoke checks.

## Release boundary

This is a self-hosted prototype with tested runtime behaviors, not a production certification. Agent authentication, admin authorization, full MCP session transport, streaming completions, replica coordination and durable audits remain unimplemented. The site deliberately states those limits. Professional presentation must not hide operational constraints.
