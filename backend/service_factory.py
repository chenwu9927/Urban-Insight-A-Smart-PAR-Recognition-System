from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, FastAPI

from .runtime import (
    apply_saved_llm_config,
    attach_recognizer,
    configure_cors,
    is_contract_export_mode,
    mount_thumbnails,
    mount_uploads,
    prepare_runtime,
)


def create_service_app(
    *,
    title: str,
    service_name: str,
    routers: Iterable[APIRouter],
    load_llm_config: bool = False,
    with_recognizer: bool = False,
    serve_uploads: bool = False,
    serve_thumbnails: bool = False,
) -> FastAPI:
    contract_export_mode = is_contract_export_mode()

    if not contract_export_mode:
        prepare_runtime()

    app = FastAPI(title=title)
    configure_cors(app)

    if load_llm_config and not contract_export_mode:
        apply_saved_llm_config()

    if with_recognizer and not contract_export_mode:
        attach_recognizer(app)

    if serve_uploads and not contract_export_mode:
        mount_uploads(app)

    if serve_thumbnails and not contract_export_mode:
        mount_thumbnails(app)

    for router in routers:
        app.include_router(router)

    @app.get("/")
    def read_root():
        return {"service": service_name, "status": "ok"}

    @app.get("/health")
    def healthcheck():
        return {"service": service_name, "status": "healthy"}

    return app
