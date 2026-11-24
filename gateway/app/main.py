import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .breaker import Breaker
from .config import Settings
from .flagsmith_client import ControlPlane
from .routes import admin, llm_proxy, mcp_proxy
from .telemetry import Telemetry

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings, http, control=None):
        self.settings, self.http = settings, http
        self.control = control or ControlPlane(settings, http)
        self.breaker, self.telemetry = Breaker(), Telemetry()
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.pending_kills = set()
        self.agent_locks = {}

    @asynccontextmanager
    async def agent_budget(self, agent):
        lock, users = self.agent_locks.get(agent, (asyncio.Lock(), 0))
        self.agent_locks[agent] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            _, users = self.agent_locks[agent]
            if users == 1:
                del self.agent_locks[agent]
            else:
                self.agent_locks[agent] = (lock, users - 1)

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def trip(self, agent, reason):
        if agent not in self.breaker.quarantine:
            self.breaker.trip(agent, reason)
            self.telemetry.emit("TRIPPED", agent, reason)
            self.spawn(self.sync(agent))

    async def sync(self, agent):
        async with self.lock:
            if agent not in self.breaker.quarantine:
                return
            try:
                await self.control.quarantine(agent, True)
                self.breaker.quarantine[agent]["synced"] = True
                await self.control.incident(agent, self.breaker.quarantine[agent]["reason"])
                self.telemetry.emit("QUARANTINED", agent, "Persisted in Flagsmith segment")
            except Exception as exc:
                log.warning("Quarantine sync failed: %s", exc)
                self.telemetry.emit("SYNC_ERROR", agent, str(exc))

    async def kill(self, resource):
        async with self.lock:
            try:
                await self.control.kill(resource)
                self.pending_kills.discard(resource)
                self.breaker.global_disabled.discard(resource)
                self.telemetry.emit("GLOBAL_KILL", "system", resource)
            except Exception as exc:
                log.warning("Global kill sync failed: %s", exc)

    def record_result(self, agent, tenant, resource, success, policy):
        local, global_trip = self.breaker.record_result(agent, tenant, resource, success, policy)
        if local:
            self.trip(agent, "upstream_error_burst")
        if global_trip and resource not in self.pending_kills:
            self.breaker.global_disabled.add(resource)
            self.pending_kills.add(resource)
            self.spawn(self.kill(resource))

    async def reconcile(self):
        while True:
            await asyncio.sleep(5)
            self.breaker.sweep()
            for agent, item in list(self.breaker.quarantine.items()):
                if not item["synced"]:
                    await self.sync(agent)
            for resource in list(self.pending_kills):
                await self.kill(resource)


def create_app(settings=None, control=None, transport=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=10, transport=transport) as http:
            runtime = Runtime(settings, http, control)
            app.state.runtime = runtime
            await runtime.control.start()
            for agent in await runtime.control.members():
                runtime.breaker.trip(agent, "persisted_quarantine")
                runtime.breaker.quarantine[agent]["synced"] = True
            maintenance = asyncio.create_task(runtime.reconcile())
            try:
                yield
            finally:
                maintenance.cancel()
                for task in list(runtime.tasks):
                    task.cancel()
                await asyncio.gather(maintenance, *runtime.tasks, return_exceptions=True)
                if runtime.control.sdk:
                    await asyncio.to_thread(runtime.control.sdk.close)

    app = FastAPI(title="RelayQuell", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-AgentBreaker-Model", "X-AgentBreaker-Tier", "X-AgentBreaker-Eval-Ms"],
    )
    app.include_router(mcp_proxy.router)
    app.include_router(llm_proxy.router)
    app.include_router(admin.router)
    return app


app = create_app()
