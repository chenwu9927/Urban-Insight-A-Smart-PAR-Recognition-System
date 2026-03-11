from agent.control_plane.routers import approvals, deliveries, runs, scheduled_tasks, sessions
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Agent Control Plane",
    service_name="agent-control-plane",
    routers=[
        sessions.router,
        runs.router,
        scheduled_tasks.router,
        approvals.router,
        deliveries.router,
    ],
)
