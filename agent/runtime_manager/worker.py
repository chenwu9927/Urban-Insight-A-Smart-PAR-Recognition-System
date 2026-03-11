from __future__ import annotations

import threading
import time

from agent.runtime_manager.client import ControlPlaneClient
from agent.runtime_manager.config import RuntimeManagerSettings
from agent.runtime_manager.executor import ExecutorClient


class HeartbeatLoop:
    def __init__(
        self,
        client: ControlPlaneClient,
        *,
        run_id: str,
        worker_id: str,
        lease_seconds: int,
        heartbeat_seconds: int,
    ) -> None:
        self.client = client
        self.run_id = run_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.progress = 5
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def update_progress(self, progress: int) -> None:
        self.progress = max(0, min(99, progress))

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                self.client.heartbeat_run(
                    run_id=self.run_id,
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                    progress=self.progress,
                )
            except Exception as exc:
                print(f"[agent-runtime] heartbeat failed for run {self.run_id}: {exc}")


class RuntimeManager:
    def __init__(self, settings: RuntimeManagerSettings | None = None) -> None:
        self.settings = settings or RuntimeManagerSettings()
        self.control_plane = ControlPlaneClient(
            self.settings.control_plane_url,
            timeout_seconds=self.settings.timeout_seconds,
        )
        self.executor = ExecutorClient(self.settings)

    def close(self) -> None:
        self.executor.close()
        self.control_plane.close()

    def run_forever(self) -> None:
        print(f"[agent-runtime] worker started: {self.settings.worker_id}")
        try:
            while True:
                handled = self.run_once()
                if not handled:
                    time.sleep(self.settings.poll_seconds)
        finally:
            self.close()

    def run_once(self) -> bool:
        claim = self.control_plane.claim_run(
            worker_id=self.settings.worker_id,
            lease_seconds=self.settings.lease_seconds,
            schedule_modes=self.settings.schedule_modes,
        )
        if not claim.get("claimed"):
            return False

        run = claim.get("run") or {}
        run_id = run.get("id")
        if not run_id:
            return False

        print(f"[agent-runtime] claimed run: {run_id}")
        heartbeat = HeartbeatLoop(
            self.control_plane,
            run_id=run_id,
            worker_id=self.settings.worker_id,
            lease_seconds=self.settings.lease_seconds,
            heartbeat_seconds=self.settings.heartbeat_seconds,
        )

        try:
            self.control_plane.heartbeat_run(
                run_id=run_id,
                worker_id=self.settings.worker_id,
                lease_seconds=self.settings.lease_seconds,
                progress=5,
            )
            heartbeat.start()
            heartbeat.update_progress(30)
            output_payload, result_summary = self.executor.execute(claim)
            heartbeat.update_progress(90)
            self.control_plane.complete_run(
                run_id=run_id,
                worker_id=self.settings.worker_id,
                output_payload=output_payload,
                result_summary=result_summary,
            )
            print(f"[agent-runtime] completed run: {run_id}")
        except Exception as exc:
            self.control_plane.fail_run(
                run_id=run_id,
                worker_id=self.settings.worker_id,
                error_message=str(exc),
            )
            print(f"[agent-runtime] failed run {run_id}: {exc}")
        finally:
            heartbeat.stop()

        return True
