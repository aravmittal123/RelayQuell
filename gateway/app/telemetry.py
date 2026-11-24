import asyncio
import json
import time
from collections import deque

from .models import TelemetryEvent


class Telemetry:
    def __init__(self):
        self.events = deque(maxlen=1000)
        self.subscribers: set[asyncio.Queue] = set()
        self.sequence = 0
        self.total = 0
        self.blocked = 0
        self.saved = 0.0

    def emit(self, kind, agent, detail, **data):
        self.sequence += 1
        event = TelemetryEvent(
            id=self.sequence, timestamp=time.time(), type=kind, agent_id=agent, detail=detail, data=data
        ).model_dump()
        self.events.append(event)
        if kind == "BLOCKED":
            self.blocked += 1
            self.saved += data.get("estimated_usd", 0.0)
        for queue in tuple(self.subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
        return event

    async def stream(self, after=0):
        queue = asyncio.Queue(maxsize=256)
        self.subscribers.add(queue)
        try:
            for event in list(self.events):
                if event["id"] > after:
                    yield f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            self.subscribers.discard(queue)
