from __future__ import annotations

import datetime
import os
import threading
import time

from agent.connectors.email.service import EmailConnectorService
from agent.models import AgentAlert
from agent.runtime_manager.config import RuntimeManagerSettings
from agent.runtime_manager.worker import RuntimeManager
from agent.scheduler.config import SchedulerSettings
from agent.scheduler.worker import AgentScheduler
from backend.database import SessionLocal


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


class AgentServiceRuntime:
    """Runs scheduler, executor dispatch, and outbound email in one process."""

    def __init__(self) -> None:
        self.enable_runtime = _env_bool("AGENT_SERVICE_ENABLE_RUNTIME", True)
        self.enable_scheduler = _env_bool("AGENT_SERVICE_ENABLE_SCHEDULER", True)
        self.enable_email_poller = _env_bool("AGENT_SERVICE_ENABLE_EMAIL_POLLER", True)
        self.enable_supervisor = _env_bool("AGENT_SERVICE_ENABLE_SUPERVISOR", True)
        self.startup_delay_seconds = max(0.0, _env_float("AGENT_SERVICE_STARTUP_DELAY_SECONDS", 2.0))
        self.supervisor_poll_seconds = max(2, _env_int("AGENT_SERVICE_SUPERVISOR_POLL_SECONDS", 5))
        self.loop_stale_seconds = max(10, _env_int("AGENT_SERVICE_LOOP_STALE_SECONDS", 45))
        self.started_at = datetime.datetime.utcnow()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._threads_by_name: dict[str, threading.Thread] = {}
        self._loop_targets = {
            "runtime": self._runtime_loop,
            "scheduler": self._scheduler_loop,
            "email": self._email_loop,
        }
        self._loop_state = {
            "runtime": {
                "enabled": self.enable_runtime,
                "last_seen_at": None,
                "last_error": None,
                "restart_count": 0,
                "last_restart_at": None,
                "open_alert_rules": set(),
            },
            "scheduler": {
                "enabled": self.enable_scheduler,
                "last_seen_at": None,
                "last_error": None,
                "restart_count": 0,
                "last_restart_at": None,
                "open_alert_rules": set(),
            },
            "email": {
                "enabled": self.enable_email_poller,
                "last_seen_at": None,
                "last_error": None,
                "restart_count": 0,
                "last_restart_at": None,
                "open_alert_rules": set(),
            },
        }
        self.runtime_manager = RuntimeManager(RuntimeManagerSettings()) if self.enable_runtime else None
        self.scheduler = AgentScheduler(SchedulerSettings()) if self.enable_scheduler else None
        self.email_service = EmailConnectorService() if self.enable_email_poller else None

    def start(self) -> None:
        if self.runtime_manager is not None:
            self._start_loop("runtime")
        if self.scheduler is not None:
            self._start_loop("scheduler")
        if self.email_service is not None:
            self._start_loop("email")
        if self.enable_supervisor and any(item["enabled"] for item in self._loop_state.values()):
            self._start_thread("agent-supervisor", self._supervisor_loop)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5)
        if self.runtime_manager is not None:
            self.runtime_manager.close()
        if self.scheduler is not None:
            self.scheduler.close()
        if self.email_service is not None:
            self.email_service.close()

    def _start_thread(self, name: str, target) -> None:
        thread = threading.Thread(name=name, target=target, daemon=True)
        with self._lock:
            self._threads.append(thread)
            self._threads_by_name[name] = thread
        thread.start()

    def _loop_thread_name(self, key: str) -> str:
        return "agent-email" if key == "email" else f"agent-{key}"

    def _start_loop(self, key: str) -> None:
        if key not in self._loop_targets:
            return
        with self._lock:
            if not self._loop_state[key]["enabled"]:
                return
            existing = self._threads_by_name.get(self._loop_thread_name(key))
            if existing and existing.is_alive():
                return
        self._start_thread(self._loop_thread_name(key), self._loop_targets[key])

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            loops = {}
            for key, value in self._loop_state.items():
                thread_name = self._loop_thread_name(key)
                thread = self._threads_by_name.get(thread_name)
                open_alert_rules = sorted(value["open_alert_rules"])
                if not value["enabled"]:
                    health = "disabled"
                elif thread and thread.is_alive() and not value["last_seen_at"]:
                    health = "starting"
                elif thread and thread.is_alive() and not open_alert_rules and not value["last_error"]:
                    health = "healthy"
                elif self._stop.is_set():
                    health = "stopping"
                elif thread and thread.is_alive():
                    health = "degraded"
                else:
                    health = "down"
                loops[key] = {
                    "enabled": value["enabled"],
                    "thread_alive": bool(thread and thread.is_alive()),
                    "last_seen_at": value["last_seen_at"].isoformat() if value["last_seen_at"] else None,
                    "last_error": value["last_error"],
                    "restart_count": value["restart_count"],
                    "last_restart_at": value["last_restart_at"].isoformat() if value["last_restart_at"] else None,
                    "open_alert_rules": open_alert_rules,
                    "health": health,
                }
            return {
                "started_at": self.started_at.isoformat(),
                "stop_requested": self._stop.is_set(),
                "supervisor_enabled": self.enable_supervisor,
                "supervisor_poll_seconds": self.supervisor_poll_seconds,
                "loop_stale_seconds": self.loop_stale_seconds,
                "loops": loops,
            }

    def _mark_loop_ok(self, key: str) -> None:
        now = _utcnow()
        with self._lock:
            open_rules = set(self._loop_state[key]["open_alert_rules"])
            self._loop_state[key]["last_seen_at"] = now
            self._loop_state[key]["last_error"] = None
        if "loop_error" in open_rules:
            self._resolve_runtime_alert(key, "loop_error", f"Recovered at {now.isoformat()}.")
        if "thread_dead" in open_rules:
            self._resolve_runtime_alert(key, "thread_dead", f"Loop is alive again as of {now.isoformat()}.")
        if "loop_stale" in open_rules:
            self._resolve_runtime_alert(key, "loop_stale", f"Heartbeat resumed at {now.isoformat()}.")

    def _mark_loop_error(self, key: str, exc: Exception) -> None:
        now = _utcnow()
        message = str(exc) or exc.__class__.__name__
        with self._lock:
            self._loop_state[key]["last_seen_at"] = now
            self._loop_state[key]["last_error"] = message
        self._raise_runtime_alert(
            key,
            "loop_error",
            severity="warning",
            summary=f"{key} loop iteration failed",
            evidence_summary=f"{exc.__class__.__name__}: {message}",
        )

    def _record_restart(self, key: str) -> None:
        with self._lock:
            self._loop_state[key]["restart_count"] += 1
            self._loop_state[key]["last_restart_at"] = _utcnow()

    def _alert_dedup_key(self, loop_key: str, rule: str) -> str:
        return f"service_loop:{loop_key}:{rule}"

    def _append_resolution_note(self, existing: str | None, note: str | None) -> str | None:
        if not note:
            return existing
        if not existing:
            return note
        if note in existing:
            return existing
        return f"{existing}\n\n{note}"

    def _raise_runtime_alert(
        self,
        loop_key: str,
        rule: str,
        *,
        severity: str,
        summary: str,
        evidence_summary: str | None = None,
    ) -> None:
        dedup_key = self._alert_dedup_key(loop_key, rule)
        now = _utcnow()
        with self._lock:
            self._loop_state[loop_key]["open_alert_rules"].add(rule)

        db = SessionLocal()
        try:
            alert = (
                db.query(AgentAlert)
                .filter(AgentAlert.dedup_key == dedup_key, AgentAlert.status == "open")
                .order_by(AgentAlert.detected_at.desc(), AgentAlert.created_at.desc())
                .first()
            )
            if alert is None:
                alert = AgentAlert(
                    source_rule=rule,
                    severity=severity,
                    status="open",
                    dedup_key=dedup_key,
                    summary=summary,
                    evidence_summary=evidence_summary,
                    scope_type="service_loop",
                    scope_id=loop_key,
                    detected_at=now,
                )
                db.add(alert)
            else:
                alert.severity = severity
                alert.summary = summary
                alert.evidence_summary = evidence_summary
                alert.detected_at = now
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"[agent-service] failed to persist alert {dedup_key}: {exc}")
        finally:
            db.close()

    def _resolve_runtime_alert(self, loop_key: str, rule: str, resolution_summary: str | None = None) -> None:
        dedup_key = self._alert_dedup_key(loop_key, rule)
        with self._lock:
            self._loop_state[loop_key]["open_alert_rules"].discard(rule)

        db = SessionLocal()
        try:
            alert = (
                db.query(AgentAlert)
                .filter(AgentAlert.dedup_key == dedup_key, AgentAlert.status == "open")
                .order_by(AgentAlert.detected_at.desc(), AgentAlert.created_at.desc())
                .first()
            )
            if alert is None:
                return
            alert.status = "resolved"
            alert.evidence_summary = self._append_resolution_note(alert.evidence_summary, resolution_summary)
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"[agent-service] failed to resolve alert {dedup_key}: {exc}")
        finally:
            db.close()

    def _supervisor_loop(self) -> None:
        if self.startup_delay_seconds:
            if self._stop.wait(self.startup_delay_seconds):
                return
        while not self._stop.is_set():
            now = _utcnow()
            for key, target in self._loop_targets.items():
                with self._lock:
                    enabled = self._loop_state[key]["enabled"]
                    last_seen_at = self._loop_state[key]["last_seen_at"]
                    open_rules = set(self._loop_state[key]["open_alert_rules"])
                    thread = self._threads_by_name.get(self._loop_thread_name(key))
                if not enabled:
                    continue
                if not thread or not thread.is_alive():
                    self._raise_runtime_alert(
                        key,
                        "thread_dead",
                        severity="critical",
                        summary=f"{key} loop stopped unexpectedly",
                        evidence_summary=f"Thread {self._loop_thread_name(key)} is not alive. Automatic restart triggered.",
                    )
                    self._record_restart(key)
                    self._start_thread(self._loop_thread_name(key), target)
                    continue
                if last_seen_at is not None:
                    stale_seconds = (now - last_seen_at).total_seconds()
                    if stale_seconds > self.loop_stale_seconds:
                        self._raise_runtime_alert(
                            key,
                            "loop_stale",
                            severity="warning",
                            summary=f"{key} loop heartbeat is stale",
                            evidence_summary=f"Last heartbeat was {int(stale_seconds)} seconds ago at {last_seen_at.isoformat()}.",
                        )
                        continue
                if "loop_stale" in open_rules:
                    self._resolve_runtime_alert(key, "loop_stale", f"Heartbeat healthy at {now.isoformat()}.")
            if self._stop.wait(self.supervisor_poll_seconds):
                break

    def _runtime_loop(self) -> None:
        assert self.runtime_manager is not None
        time.sleep(self.startup_delay_seconds)
        while not self._stop.is_set():
            try:
                handled = self.runtime_manager.run_once()
                self._mark_loop_ok("runtime")
                wait_seconds = 0.5 if handled else self.runtime_manager.settings.poll_seconds
            except Exception as exc:
                self._mark_loop_error("runtime", exc)
                print(f"[agent-service] runtime loop failed: {exc}")
                wait_seconds = 2.0
            if self._stop.wait(wait_seconds):
                break

    def _scheduler_loop(self) -> None:
        assert self.scheduler is not None
        time.sleep(self.startup_delay_seconds)
        while not self._stop.is_set():
            try:
                self.scheduler.run_once()
                self._mark_loop_ok("scheduler")
                wait_seconds = self.scheduler.settings.poll_seconds
            except Exception as exc:
                self._mark_loop_error("scheduler", exc)
                print(f"[agent-service] scheduler loop failed: {exc}")
                wait_seconds = 2.0
            if self._stop.wait(wait_seconds):
                break

    def _email_loop(self) -> None:
        assert self.email_service is not None
        time.sleep(self.startup_delay_seconds)
        poll_seconds = self.email_service.settings.poll_seconds
        while not self._stop.is_set():
            try:
                created, details = self.email_service.process_outbound_once()
                self._mark_loop_ok("email")
                if created:
                    print(f"[agent-service] outbound email deliveries: {created}; details={details}")
            except Exception as exc:
                self._mark_loop_error("email", exc)
                print(f"[agent-service] email poll failed: {exc}")
            if self._stop.wait(poll_seconds):
                break
