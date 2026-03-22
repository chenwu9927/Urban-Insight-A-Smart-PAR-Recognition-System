from backend.routers import auth
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Auth Service",
    service_name="auth-service",
    routers=[auth.router],
)
