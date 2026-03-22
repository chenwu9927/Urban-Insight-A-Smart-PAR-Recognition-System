from backend.routers import insights, settings, stats
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Insight Service",
    service_name="insight-service",
    routers=[stats.router, insights.router, settings.router],
    load_llm_config=True,
)
