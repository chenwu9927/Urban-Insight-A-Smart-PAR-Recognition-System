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


class SchedulerSettings:
    def __init__(self) -> None:
        self.control_plane_url = os.getenv("AGENT_CONTROL_PLANE_URL", "http://agent-control-plane:8000").rstrip("/")
        self.poll_seconds = max(2, _env_int("AGENT_SCHEDULER_POLL_SECONDS", 10))
        self.dispatch_limit = max(1, _env_int("AGENT_SCHEDULER_DISPATCH_LIMIT", 20))
