from __future__ import annotations

import os

from fastapi import HTTPException

from agent.service_runtime import AgentServiceRuntime
from backend.service_factory import create_service_app

_service_base_url = os.getenv("AGENT_SERVICE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
os.environ.setdefault("AGENT_CONTROL_PLANE_URL", _service_base_url)
os.environ.setdefault("AGENT_EXECUTOR_URL", _service_base_url)

from agent.connectors.email.router import router as email_router, service as email_service  # noqa: E402
from agent.control_plane.routers import alerts, approvals, deliveries, events, goals, overview, runs, scheduled_tasks, sessions, subscriptions, tools  # noqa: E402
from agent.executor.router import router as executor_router, service as executor_service  # noqa: E402


app = create_service_app(
    title="UrbanInsight Agent Service",
    service_name="agent-service",
    routers=[
        sessions.router,
        tools.router,
        alerts.router,
        goals.router,
        events.router,
        subscriptions.router,
        overview.router,
        runs.router,
        scheduled_tasks.router,
        approvals.router,
        deliveries.router,
        email_router,
        executor_router,
    ],
)

_runtime: AgentServiceRuntime | None = None


@app.on_event("startup")
def startup_agent_runtime() -> None:
    global _runtime
    _runtime = AgentServiceRuntime()
    _runtime.start()


@app.on_event("shutdown")
def shutdown_agent_runtime() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None
    email_service.close()
    executor_service.close()


@app.get("/agent/runtime-status")
def get_agent_runtime_status() -> dict[str, object]:
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Agent runtime is not available")
    return _runtime.snapshot()
