from __future__ import annotations

import datetime
import json
import re
import smtplib
import threading
import time
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from agent.connectors.email.config import EmailConnectorSettings
from agent.connectors.email.control_plane_client import EmailControlPlaneClient

APPROVAL_SUBJECT_RE = re.compile(r"\[APPROVAL:(?P<approval_id>[A-Za-z0-9-]+)\]", re.IGNORECASE)


def utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _infer_decision(text: str) -> str | None:
    value = (text or "").strip().lower()
    if not value:
        return None
    if any(token in value for token in ["approve", "approved", "同意", "批准", "通过", "yes"]):
        return "approved"
    if any(token in value for token in ["reject", "rejected", "拒绝", "驳回", "deny", "no"]):
        return "rejected"
    return None


def _subject_result(subject: str) -> str:
    return f"[RESULT] {subject}".strip()


def _subject_ack(subject: str) -> str:
    return f"[ACK] {subject}".strip()


class EmailDeliveryGateway:
    def __init__(self, settings: EmailConnectorSettings) -> None:
        self.settings = settings
        self.settings.outbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, *, to_address: str, subject: str, body: str, thread_key: str | None = None) -> dict[str, Any]:
        if self.settings.delivery_mode == "smtp":
            self._send_smtp(to_address=to_address, subject=subject, body=body)
            return {
                "delivery_mode": "smtp",
                "target_address": to_address,
                "subject": subject,
                "thread_key": thread_key,
            }

        path = self._write_outbox(to_address=to_address, subject=subject, body=body, thread_key=thread_key)
        return {
            "delivery_mode": "log",
            "target_address": to_address,
            "subject": subject,
            "thread_key": thread_key,
            "outbox_path": str(path),
        }

    def _send_smtp(self, *, to_address: str, subject: str, body: str) -> None:
        if not self.settings.smtp_host:
            raise ValueError("SMTP host is not configured")
        message = EmailMessage()
        message["From"] = self.settings.default_from_address
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as server:
            if self.settings.smtp_use_tls:
                server.starttls()
            if self.settings.smtp_username:
                server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.send_message(message)

    def _write_outbox(self, *, to_address: str, subject: str, body: str, thread_key: str | None) -> Path:
        timestamp = utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{uuid.uuid4().hex}.json"
        path = self.settings.outbox_dir / filename
        payload = {
            "from_address": self.settings.default_from_address,
            "to_address": to_address,
            "subject": subject,
            "thread_key": thread_key,
            "body": body,
            "created_at": utcnow().isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


class EmailConnectorService:
    def __init__(self, settings: EmailConnectorSettings | None = None) -> None:
        self.settings = settings or EmailConnectorSettings()
        self.control_plane = EmailControlPlaneClient(self.settings.control_plane_url)
        self.delivery = EmailDeliveryGateway(self.settings)

    def close(self) -> None:
        self.control_plane.close()

    def ingest_email(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        subject = str(payload.get("subject") or "").strip()
        text = str(payload.get("text") or "").strip()
        approval_id = str(payload.get("approval_id") or "").strip() or self._parse_approval_id(subject)
        decision = str(payload.get("decision") or "").strip() or _infer_decision(text)

        if approval_id:
            answer_payload = {
                "status": decision or "approved",
                "answers": payload.get("answers") or {"source": "email", "text": text},
            }
            answered = self.control_plane.answer_approval(approval_id, answer_payload)
            recipient = str(payload.get("from_address") or "").strip()
            if recipient:
                self._send_and_record(
                    to_address=recipient,
                    subject=_subject_ack(subject or f"APPROVAL {approval_id}"),
                    body=f"Approval {approval_id} has been recorded with status: {answered['status']}.",
                    thread_key=str(payload.get("thread_key") or approval_id),
                    dedup_key=f"approval-answer-ack:{approval_id}:{answered['status']}",
                    message_type="approval_answer_ack",
                )
            return answered, "approval"

        session_id = str(payload.get("session_id") or "").strip()
        if session_id:
            session = self.control_plane.get_session(session_id)
        else:
            session_payload = {
                "kind": "command",
                "title": subject or "Email Task",
                "status": "active",
                "source": "email",
                "config_snapshot": {
                    "email": {
                        "from_address": payload.get("from_address"),
                        "subject": subject,
                        "thread_key": payload.get("thread_key"),
                        "connector_message_id": payload.get("connector_message_id"),
                        "metadata": payload.get("metadata") or {},
                    }
                },
            }
            session = self.control_plane.create_session(session_payload)

        message_payload = {
            "role": "user",
            "content": {"text": text},
            "text_preview": text[:500],
            "connector": "email",
            "connector_message_id": payload.get("connector_message_id"),
            "thread_key": payload.get("thread_key"),
        }
        message = self.control_plane.create_message(session["id"], message_payload)

        run_payload = {
            "session_id": session["id"],
            "trigger_message_id": message["id"],
            "schedule_mode": "immediate",
            "permission_mode": "default",
            "prompt": text,
        }
        action = str(payload.get("action") or "").strip()
        if action:
            run_payload["input_payload"] = {
                "action": action,
                "params": payload.get("params") or {},
            }

        run = self.control_plane.create_run(run_payload)
        recipient = str(payload.get("from_address") or "").strip()
        if recipient:
            self._send_and_record(
                to_address=recipient,
                subject=_subject_ack(subject or "Email Task"),
                body=f"Your task has been accepted.\n\nSession: {session['id']}\nRun: {run['id']}",
                thread_key=str(payload.get("thread_key") or run["id"]),
                dedup_key=f"email-ack:{run['id']}",
                message_type="email_ack",
                related_run_id=run["id"],
            )
        return {"session": session, "run": run}, "run"

    def process_outbound_once(self) -> tuple[int, list[str]]:
        created = 0
        details: list[str] = []
        created_delta, detail_delta = self._process_runs(status="completed")
        created += created_delta
        details.extend(detail_delta)
        created_delta, detail_delta = self._process_runs(status="failed")
        created += created_delta
        details.extend(detail_delta)
        created_delta, detail_delta = self._process_pending_approvals()
        created += created_delta
        details.extend(detail_delta)
        return created, details

    def _process_runs(self, *, status: str) -> tuple[int, list[str]]:
        deliveries = 0
        details: list[str] = []
        runs = self.control_plane.list_runs(status=status, limit=100)
        for run in runs:
            session = self.control_plane.get_session(run["session_id"])
            email_meta = ((session.get("config_snapshot") or {}).get("email") or {})
            recipient = str(email_meta.get("from_address") or "").strip()
            if session.get("source") != "email" or not recipient:
                continue
            dedup_key = f"run-{status}:{run['id']}"
            if self._delivery_exists(dedup_key):
                continue
            subject = _subject_result(str(email_meta.get("subject") or session.get("title") or "Agent Task"))
            body = self._format_run_body(run)
            self._send_and_record(
                to_address=recipient,
                subject=subject,
                body=body,
                thread_key=str(email_meta.get("thread_key") or run["id"]),
                dedup_key=dedup_key,
                message_type=f"run_{status}",
                related_run_id=run["id"],
            )
            deliveries += 1
            details.append(f"sent {status} email for run {run['id']}")
        return deliveries, details

    def _process_pending_approvals(self) -> tuple[int, list[str]]:
        deliveries = 0
        details: list[str] = []
        approvals = self.control_plane.list_approvals(status="pending", limit=100)
        for approval in approvals:
            session = self.control_plane.get_session(approval["session_id"])
            email_meta = ((session.get("config_snapshot") or {}).get("email") or {})
            recipient = str(email_meta.get("from_address") or "").strip()
            if session.get("source") != "email" or not recipient:
                continue
            dedup_key = f"approval-pending:{approval['id']}"
            if self._delivery_exists(dedup_key):
                continue
            subject = f"[APPROVAL:{approval['id']}] Approval required"
            body = self._format_approval_body(approval)
            self._send_and_record(
                to_address=recipient,
                subject=subject,
                body=body,
                thread_key=str(email_meta.get("thread_key") or approval["id"]),
                dedup_key=dedup_key,
                message_type="approval_pending",
                related_run_id=approval["run_id"],
            )
            deliveries += 1
            details.append(f"sent approval email for approval {approval['id']}")
        return deliveries, details

    def _delivery_exists(self, dedup_key: str) -> bool:
        deliveries = self.control_plane.list_deliveries(
            connector="email",
            delivery_status="sent",
            dedup_key=dedup_key,
            limit=1,
        )
        return bool(deliveries)

    def _send_and_record(
        self,
        *,
        to_address: str,
        subject: str,
        body: str,
        thread_key: str | None,
        dedup_key: str,
        message_type: str,
        related_run_id: str | None = None,
    ) -> None:
        try:
            payload = self.delivery.send(
                to_address=to_address,
                subject=subject,
                body=body,
                thread_key=thread_key,
            )
            self.control_plane.create_delivery(
                {
                    "connector": "email",
                    "direction": "outbound",
                    "message_type": message_type,
                    "delivery_status": "sent",
                    "dedup_key": dedup_key,
                    "thread_key": thread_key,
                    "source_address": self.settings.default_from_address,
                    "target_address": to_address,
                    "subject": subject,
                    "payload": payload,
                    "related_run_id": related_run_id,
                    "sent_at": utcnow().isoformat(),
                }
            )
        except Exception as exc:
            self.control_plane.create_delivery(
                {
                    "connector": "email",
                    "direction": "outbound",
                    "message_type": message_type,
                    "delivery_status": "failed",
                    "dedup_key": dedup_key,
                    "thread_key": thread_key,
                    "source_address": self.settings.default_from_address,
                    "target_address": to_address,
                    "subject": subject,
                    "payload": {"error": str(exc)},
                    "related_run_id": related_run_id,
                    "failed_at": utcnow().isoformat(),
                }
            )
            raise

    @staticmethod
    def _parse_approval_id(subject: str) -> str:
        match = APPROVAL_SUBJECT_RE.search(subject or "")
        if not match:
            return ""
        return match.group("approval_id").strip()

    @staticmethod
    def _format_run_body(run: dict[str, Any]) -> str:
        summary = str(run.get("result_summary") or "").strip() or "No summary available."
        output_payload = run.get("output_payload")
        output_block = ""
        if output_payload is not None:
            output_block = "\n\nOutput payload:\n" + json.dumps(output_payload, ensure_ascii=False, indent=2)
        return f"Run {run['id']} finished with status: {run['status']}.\n\nSummary:\n{summary}{output_block}"

    @staticmethod
    def _format_approval_body(approval: dict[str, Any]) -> str:
        tool_input = json.dumps(approval.get("tool_input") or {}, ensure_ascii=False, indent=2)
        return (
            f"Approval required for run {approval['run_id']}.\n\n"
            f"Tool: {approval['tool_name']}\n"
            f"Risk: {approval['risk_level']}\n"
            f"Reason: {approval.get('reason') or 'N/A'}\n\n"
            f"Tool input:\n{tool_input}\n\n"
            f"Reply with subject [APPROVAL:{approval['id']}] and body 'approved' or 'rejected'."
        )


class EmailBackgroundPoller:
    def __init__(self, service: EmailConnectorService, *, poll_seconds: int) -> None:
        self.service = service
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                created, details = self.service.process_outbound_once()
                if created:
                    print(f"[agent-email] created deliveries: {created}; details={details}")
            except Exception as exc:
                print(f"[agent-email] background poll failed: {exc}")
