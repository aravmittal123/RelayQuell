# Vaeltrixis: demo voiceover

Target: 2:45–2:55, 16:9. Record this voiceover yourself. The requested final video should have no narration track and no subtitles; on-screen product labels are visual identifiers, not subtitles. Timings are approximate and depend on delivery.

## 0:00–0:20 — The problem

An AI agent can call tools faster than a person can react. If it gets stuck repeating the same action, one error can turn into dozens of calls. And if we shut down the whole service to stop it, healthy agents go down too. How do we stop the runaway agent without stopping everyone else?

Visual: two streams of tool requests; one accelerates and loops. A red interruption contains only that stream. Avoid fabricated dollar amounts.

## 0:20–0:45 — The solution

Meet Vaeltrixis: a self-hosted runtime control gateway for tool-using agents. It sits between agents and their tools and language models. Its control plane is a real, self-hosted Flagsmith instance, so operators can change policies and routes without redeploying the gateway.

Visual: agent → gateway → mock MCP and LLM; Flagsmith and PostgreSQL run beside the gateway in Docker. Show actual container status.

## 0:45–1:20 — Live containment

Here are two agents using the same tool. The healthy agent sends different requests. The runaway agent repeats the same request. On the third identical call, Vaeltrixis opens that agent's circuit immediately. The call is blocked before it reaches the tool. The healthy agent continues to work.

Visual: actual console, healthy call, trigger doom-loop, visible blocked events and healthy call after trip. Show these as real captured interactions.

## 1:20–1:50 — Flagsmith does real work

The gateway writes the offending agent's identifier into the Flagsmith quarantine segment and refreshes its local environment document. That segment disables the payment tool and selects a smaller model route for the quarantined identity. In the console, we can see the sync status and the model change from GPT-4o to GPT-4o mini.

Visual: actual Flagsmith segment and override; console sync badge and LLM routing. Avoid showing keys, webhook URL, or other secrets.

## 1:50–2:15 — Policy rehearsal and recovery

Before changing the live loop policy, we can replay a trace against the current policy and a proposed threshold. This preview is isolated: it doesn't call the upstream tool or write to Flagsmith. An operator can then release the quarantined agent. The gateway removes the persisted segment membership and refreshes Flagsmith before allowing tool calls again.

Visual: actual Compare loop policies result, then release button and successful subsequent tool call.

## 2:15–2:40 — Reuse and limitations

Developers can run the stack with Docker and use deterministic mock services without paid API keys. Vaeltrixis currently supports two tool names and non-streaming OpenAI-compatible completions. It is a local prototype: authentication, full MCP transport, shared multi-worker state, and durable audit storage still need work before a public production deployment.

Visual: quickstart and repository README, followed by a brief clearly labeled prototype limitations panel.

## 2:40–2:52 — Closing

Vaeltrixis makes the control loop visible: detect the loop, isolate one agent, persist the decision in open-source Flagsmith, and recover deliberately. Explore the public repository and try the local demo.

Visual: gateway flow resolves to healthy and contained branches; end card with github.com/aravmittal123/Vaeltrixis.

Record a natural take and check the final runtime is under 3:00. The estimates are not measured voice timing.
