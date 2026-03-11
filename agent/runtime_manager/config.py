from __future__ import annotations

import os
import socket


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


class RuntimeManagerSettings:
    def __init__(self) -> None:
        self.control_plane_url = os.getenv("AGENT_CONTROL_PLANE_URL", "http://agent-control-plane:8000").rstrip("/")
        self.executor_url = os.getenv("AGENT_EXECUTOR_URL", "http://agent-executor:8000").rstrip("/")
        self.auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000").rstrip("/")
        self.media_service_url = os.getenv("MEDIA_SERVICE_URL", "http://media-service:8000").rstrip("/")
        self.analysis_service_url = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:8000").rstrip("/")
        self.search_service_url = os.getenv("SEARCH_SERVICE_URL", "http://search-service:8000").rstrip("/")
        self.insight_service_url = os.getenv("INSIGHT_SERVICE_URL", "http://insight-service:8000").rstrip("/")
        self.worker_id = os.getenv("AGENT_RUNTIME_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")
        self.lease_seconds = max(5, _env_int("AGENT_RUNTIME_LEASE_SECONDS", 60))
        self.heartbeat_seconds = max(2, _env_int("AGENT_RUNTIME_HEARTBEAT_SECONDS", 15))
        self.poll_seconds = max(1, _env_int("AGENT_RUNTIME_POLL_SECONDS", 3))
        self.timeout_seconds = max(5, _env_int("AGENT_RUNTIME_TIMEOUT_SECONDS", 30))
        self.schedule_modes = _env_list("AGENT_RUNTIME_SCHEDULE_MODES")
