import hashlib
import json
import time
from collections import defaultdict, deque

from .models import Policy


class Breaker:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.calls = defaultdict(deque)
        self.spend = defaultdict(deque)
        self.errors = defaultdict(deque)
        self.consecutive = defaultdict(int)
        self.quarantine: dict[str, dict] = {}
        self.global_disabled: set[str] = set()

    def prune(self, queue, window):
        now = self.clock()
        while queue and queue[0][0] <= now - window:
            queue.popleft()

    def record_tool_call(self, agent, tool, arguments, policy: Policy):
        signature = hashlib.sha256(
            json.dumps([tool, arguments], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        calls = self.calls[agent]
        self.prune(calls, policy.window_seconds)
        calls.append((self.clock(), signature))
        limit = max(policy.max_identical_calls, policy.max_oscillating_cycles * 2)
        while len(calls) > limit:
            calls.popleft()
        values = [item[1] for item in calls]
        n = policy.max_identical_calls
        if len(values) >= n and len(set(values[-n:])) == 1:
            return "identical_tool_loop"
        n = policy.max_oscillating_cycles * 2
        tail = values[-n:]
        if len(tail) == n and tail[0] != tail[1] and tail == tail[:2] * (n // 2):
            return "oscillating_tool_loop"
        return None

    def cost_exceeded(self, agent, policy: Policy):
        queue = self.spend[agent]
        self.prune(queue, 60)
        return (
            sum(x[1] for x in queue) >= policy.max_tokens_per_minute
            or sum(x[2] for x in queue) >= policy.max_usd_per_minute
        )

    def record_spend(self, agent, tokens, usd):
        queue = self.spend[agent]
        self.prune(queue, 60)
        queue.append((self.clock(), tokens, usd))

    def record_result(self, agent, tenant, resource, success, policy: Policy):
        key = (agent, tenant, resource)
        if success:
            self.consecutive.pop(key, None)
            return False, False
        self.consecutive[key] += 1
        errors = self.errors[resource]
        self.prune(errors, 60)
        errors.append((self.clock(), agent, tenant))
        # Require distinct agents; one agent cannot manufacture a global outage.
        global_trip = len({x[1] for x in errors}) >= policy.global_error_tenant_threshold
        return self.consecutive[key] >= policy.consecutive_error_threshold, global_trip

    def trip(self, agent, reason):
        self.quarantine.setdefault(agent, {"reason": reason, "since": time.time(), "synced": False})

    def release(self, agent):
        self.quarantine.pop(agent, None)
        self.calls.pop(agent, None)
        self.spend.pop(agent, None)
        for key in list(self.consecutive):
            if key[0] == agent:
                del self.consecutive[key]
        for resource, entries in self.errors.items():
            self.errors[resource] = deque(x for x in entries if x[1] != agent)

    def sweep(self):
        for agent, calls in list(self.calls.items()):
            self.prune(calls, 3600)
            if not calls:
                del self.calls[agent]
        for agent, spend in list(self.spend.items()):
            self.prune(spend, 60)
            if not spend:
                del self.spend[agent]
        for errors in self.errors.values():
            self.prune(errors, 60)
        active = {x[1] for entries in self.errors.values() for x in entries}
        for key in list(self.consecutive):
            if key[0] not in active:
                del self.consecutive[key]
