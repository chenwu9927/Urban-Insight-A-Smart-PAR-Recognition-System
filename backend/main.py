from .routers import analysis, auth, files, history, insights, search, settings, stats
from .service_factory import create_service_app


app = create_service_app(
    title="UrbanInsight API",
    service_name="monolith-api",
    routers=[
        auth.router,
        files.router,
        analysis.router,
        history.router,
        search.router,
        stats.router,
        insights.router,
        settings.router,
    ],
    load_llm_config=True,
    with_recognizer=True,
    serve_uploads=True,
    serve_thumbnails=True,
)
