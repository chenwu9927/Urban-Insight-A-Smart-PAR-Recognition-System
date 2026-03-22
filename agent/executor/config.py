from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class ExecutorSettings:
    def __init__(self) -> None:
        self.auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000").rstrip("/")
        self.media_service_url = os.getenv("MEDIA_SERVICE_URL", "http://media-service:8000").rstrip("/")
        self.analysis_service_url = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:8000").rstrip("/")
        self.search_service_url = os.getenv("SEARCH_SERVICE_URL", "http://search-service:8000").rstrip("/")
        self.insight_service_url = os.getenv("INSIGHT_SERVICE_URL", "http://insight-service:8000").rstrip("/")
        self.control_plane_url = os.getenv("AGENT_CONTROL_PLANE_URL", "http://agent-service:8000").rstrip("/")
        self.timeout_seconds = max(5, _env_int("AGENT_EXECUTOR_TIMEOUT_SECONDS", 30))
        self.workspace_dir = os.getenv("AGENT_WORKSPACE_DIR", "agent_workspace").strip() or "agent_workspace"
