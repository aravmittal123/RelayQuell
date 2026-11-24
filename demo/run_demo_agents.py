import asyncio
import os
import uuid

import httpx

URL = os.getenv("GATEWAY_URL", "http://localhost:8085")


async def run(agent, runaway):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{URL}/api/quarantine/release", json={"agent_id": agent})
        response.raise_for_status()
        for _ in range(6):
            response = await client.post(
                f"{URL}/mcp",
                headers={"X-Agent-Id": agent},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "charge_card",
                        "arguments": {"order_id": "loop" if runaway else uuid.uuid4().hex},
                    },
                },
            )
            print(f"{agent}: MCP HTTP {response.status_code} {response.text}")
            response = await client.post(
                f"{URL}/v1/chat/completions",
                headers={"X-Agent-Id": agent},
                json={"messages": [{"role": "user", "content": "Status?"}]},
            )
            response.raise_for_status()
            print(f"{agent}: model={response.headers.get('X-AgentBreaker-Model')}")
            await asyncio.sleep(0.5)


async def main():
    await asyncio.gather(run("agent_healthy", False), run("agent_runaway", True))


if __name__ == "__main__":
    asyncio.run(main())
