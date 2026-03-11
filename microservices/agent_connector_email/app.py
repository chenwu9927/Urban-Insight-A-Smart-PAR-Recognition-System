from agent.connectors.email.config import EmailConnectorSettings
from agent.connectors.email.router import router, service
from agent.connectors.email.service import EmailBackgroundPoller
from backend.service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight Agent Email Connector",
    service_name="agent-connector-email",
    routers=[router],
)

_poller: EmailBackgroundPoller | None = None


@app.on_event("startup")
def startup_email_poller() -> None:
    global _poller
    settings = EmailConnectorSettings()
    if not settings.enable_background:
        return
    _poller = EmailBackgroundPoller(service, poll_seconds=settings.poll_seconds)
    _poller.start()


@app.on_event("shutdown")
def shutdown_email_poller() -> None:
    global _poller
    if _poller is not None:
        _poller.stop()
        _poller = None
    service.close()
