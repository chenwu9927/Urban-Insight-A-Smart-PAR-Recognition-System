from __future__ import annotations

import time

from agent.scheduler.client import SchedulerControlPlaneClient
from agent.scheduler.config import SchedulerSettings


class AgentScheduler:
    def __init__(self, settings: SchedulerSettings | None = None) -> None:
        self.settings = settings or SchedulerSettings()
        self.client = SchedulerControlPlaneClient(self.settings.control_plane_url)

    def close(self) -> None:
        self.client.close()

    def run_once(self) -> dict:
        result = self.client.dispatch_due(limit=self.settings.dispatch_limit)
        if result.get("dispatched") or result.get("skipped"):
            print(
                "[agent-scheduler] dispatch",
                {
                    "dispatched": result.get("dispatched"),
                    "skipped": result.get("skipped"),
                    "run_ids": result.get("run_ids"),
                },
            )
        return result

    def run_forever(self) -> None:
        print("[agent-scheduler] started")
        try:
            while True:
                self.run_once()
                time.sleep(self.settings.poll_seconds)
        finally:
            self.close()
