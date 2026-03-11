from agent.executor.router import router
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Agent Executor",
    service_name="agent-executor",
    routers=[router],
)
