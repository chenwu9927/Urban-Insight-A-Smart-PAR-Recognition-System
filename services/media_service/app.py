from backend.routers import files
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Media Service",
    service_name="media-service",
    routers=[files.router],
    serve_uploads=True,
)
