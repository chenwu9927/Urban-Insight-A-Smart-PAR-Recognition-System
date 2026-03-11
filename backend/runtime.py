from __future__ import annotations

import os
from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .services.recognition import MockPedestrianRecognizer


UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
THUMBNAIL_DIR = os.getenv("THUMBNAIL_DIR", "thumbnails")


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["*"]


def ensure_storage_dirs() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def configure_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def mount_uploads(app: FastAPI) -> None:
    ensure_storage_dirs()
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def mount_thumbnails(app: FastAPI) -> None:
    ensure_storage_dirs()
    app.mount("/thumbnails", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")


def apply_saved_llm_config() -> None:
    try:
        from .database import SessionLocal
        from .routers.settings import apply_llm_config_to_env

        db = SessionLocal()
        try:
            apply_llm_config_to_env(db)
        finally:
            db.close()
        print("Loaded saved LLM config from database.")
    except Exception as exc:
        print(f"[warn] Failed to load LLM config: {exc}")


@lru_cache(maxsize=1)
def get_recognizer():
    try:
        from .services.real_recognition import RealPedestrianRecognizer  # type: ignore

        return RealPedestrianRecognizer()
    except Exception as exc:
        print(f"[warn] RealPedestrianRecognizer unavailable, using MockPedestrianRecognizer: {exc}")
        return MockPedestrianRecognizer()


def attach_recognizer(app: FastAPI) -> None:
    app.state.recognizer = get_recognizer()


def prepare_runtime() -> None:
    init_db()
    ensure_storage_dirs()
