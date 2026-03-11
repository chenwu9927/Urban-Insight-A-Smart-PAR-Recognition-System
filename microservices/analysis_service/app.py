from backend.routers import analysis, history
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Analysis Service",
    service_name="analysis-service",
    routers=[analysis.router, history.router],
    serve_thumbnails=True,
)
