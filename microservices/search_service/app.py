from backend.routers import search
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Search Service",
    service_name="search-service",
    routers=[search.router],
    with_recognizer=True,
)
