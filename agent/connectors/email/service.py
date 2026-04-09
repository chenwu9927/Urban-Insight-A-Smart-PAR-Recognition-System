from __future__ import annotations

import datetime
import imaplib
import json
import re
import smtplib
import ssl
import threading
import time
import uuid
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from agent.connectors.email.config import EmailConnectorSettings
from agent.connectors.email.control_plane_client import EmailControlPlaneClient

APPROVAL_SUBJECT_RE = re.compile(r"\[APPROVAL:(?P<approval_id>[A-Za-z0-9-]+)\]", re.IGNORECASE)
SEVERITY_RANK = {
    "info": 0,
    "warning": 1,
    "critical": 2,
}


def utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _parse_datetime(value: Any) -> datetime.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


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


def _subject_alert(alert: dict[str, Any], *, resolved: bool) -> str:
    prefix = "RESOLVED" if resolved else "ALERT"
    severity = str(alert.get("severity") or "warning").upper()
    summary = str(alert.get("summary") or "Agent alert").strip()
    return f"[{prefix}][{severity}] {summary}".strip()


def _severity_value(value: str | None) -> int:
    return SEVERITY_RANK.get(str(value or "").strip().lower(), 1)


def _decode_subject(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return str(value).strip()


def _extract_text_body(message) -> str:
    if message.is_multipart():
        parts: list[str] = []
        for part in message.walk():
            content_type = (part.get_content_type() or "").lower()
            disposition = str(part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            if content_type == "text/plain":
                try:
                    parts.append(part.get_content().strip())
                except Exception:
                    continue
        text = "\n\n".join(item for item in parts if item).strip()
        if text:
            return text

        for part in message.walk():
            content_type = (part.get_content_type() or "").lower()
            disposition = str(part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            if content_type == "text/html":
                try:
                    html = part.get_content()
                except Exception:
                    continue
                return re.sub(r"<[^>]+>", " ", html or "").strip()
        return ""

    try:
        payload = message.get_content()
    except Exception:
        return ""
    if (message.get_content_type() or "").lower() == "text/html":
        return re.sub(r"<[^>]+>", " ", payload or "").strip()
    return str(payload or "").strip()


def _normalize_email_address(value: str | None) -> str:
    return str(value or "").strip().lower()


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

        smtp_context = (
            ssl.create_default_context()
            if self.settings.smtp_verify_certificate
            else ssl._create_unverified_context()
        )
        if self.settings.smtp_use_ssl:
            server = smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=30,
                context=smtp_context,
            )
        else:
            server = smtplib.SMTP(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=30,
            )

        with server:
            if not self.settings.smtp_use_ssl and self.settings.smtp_use_tls:
                server.starttls(context=smtp_context)
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
        self.settings.state_path.parent.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.control_plane.close()

    def _is_self_address(self, value: str | None) -> bool:
        address = _normalize_email_address(value)
        if not address:
            return False
        known_addresses = {
            _normalize_email_address(self.settings.default_from_address),
            _normalize_email_address(self.settings.smtp_username),
            _normalize_email_address(self.settings.imap_username),
        }
        return address in {item for item in known_addresses if item}

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
        created_delta, detail_delta = self._process_alert_notifications()
        created += created_delta
        details.extend(detail_delta)
        return created, details

    def process_inbound_once(self) -> tuple[int, list[str]]:
        if not self.settings.imap_enable:
            return 0, []
        if not self.settings.imap_host or not self.settings.imap_username:
            return 0, ["IMAP inbound polling is enabled but not fully configured"]

        state = self._read_state()
        mailbox = self.settings.imap_mailbox
        last_uid = int(state.get(mailbox, 0) or 0)
        processed = 0
        details: list[str] = []

        client = None
        try:
            if self.settings.imap_use_ssl:
                client = imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port)
            else:
                client = imaplib.IMAP4(self.settings.imap_host, self.settings.imap_port)
            client.login(self.settings.imap_username, self.settings.imap_password)
            status, _ = client.select(mailbox)
            if status != "OK":
                raise RuntimeError(f"Unable to select mailbox {mailbox}")

            status, data = client.uid("SEARCH", None, f"UID {last_uid + 1}:*")
            if status != "OK":
                raise RuntimeError("Unable to search mailbox")

            highest_uid = last_uid
            uid_list = [item.decode("utf-8") if isinstance(item, bytes) else str(item) for item in (data[0] or b"").split()]
            for uid in uid_list:
                status, fetched = client.uid("FETCH", uid, "(RFC822)")
                if status != "OK":
                    details.append(f"failed to fetch message uid={uid}")
                    continue

                raw_message = b""
                for chunk in fetched:
                    if isinstance(chunk, tuple) and len(chunk) >= 2:
                        raw_message = chunk[1]
                        break
                if not raw_message:
                    details.append(f"empty message uid={uid}")
                    continue

                message = BytesParser(policy=policy.default).parsebytes(raw_message)
                from_address = parseaddr(message.get("Reply-To") or message.get("From") or "")[1].strip()
                subject = _decode_subject(message.get("Subject"))
                text = _extract_text_body(message)
                connector_message_id = str(message.get("Message-ID") or f"imap:{mailbox}:{uid}").strip()
                thread_key = str(message.get("In-Reply-To") or message.get("References") or connector_message_id).strip()
                dedup_key = f"inbound:{connector_message_id}"

                if self._delivery_exists(dedup_key, delivery_status=None):
                    highest_uid = max(highest_uid, int(uid))
                    continue
                if not from_address:
                    details.append(f"skipped uid={uid} without sender address")
                    highest_uid = max(highest_uid, int(uid))
                    continue
                if self._is_self_address(from_address):
                    details.append(f"skipped uid={uid} from self address {from_address}")
                    highest_uid = max(highest_uid, int(uid))
                    continue

                delivery_status = "received"
                result: dict[str, Any] | Any
                mode = "run"
                try:
                    result, mode = self.ingest_email(
                        {
                            "from_address": from_address,
                            "subject": subject,
                            "text": text,
                            "thread_key": thread_key,
                            "connector_message_id": connector_message_id,
                            "metadata": {
                                "uid": uid,
                                "mailbox": mailbox,
                                "to_address": parseaddr(message.get("To") or "")[1].strip(),
                            },
                        }
                    )
                except Exception as exc:
                    delivery_status = "failed"
                    result = {"error": str(exc)}
                    mode = "error"
                    details.append(f"failed to process inbound email uid={uid}: {exc}")

                self.control_plane.create_delivery(
                    {
                        "connector": "email",
                        "direction": "inbound",
                        "message_type": "email_inbound",
                        "delivery_status": delivery_status,
                        "dedup_key": dedup_key,
                        "thread_key": thread_key,
                        "source_address": from_address,
                        "target_address": parseaddr(message.get("To") or "")[1].strip(),
                        "subject": subject,
                        "payload": {
                            "mode": mode,
                            "connector_message_id": connector_message_id,
                            "uid": uid,
                            "result": result,
                        },
                        "sent_at": utcnow().isoformat(),
                    }
                )
                highest_uid = max(highest_uid, int(uid))
                if delivery_status == "received":
                    processed += 1
                    details.append(f"processed inbound email uid={uid} mode={mode}")

            if highest_uid > last_uid:
                state[mailbox] = highest_uid
                self._write_state(state)
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass

        return processed, details

    def _process_runs(self, *, status: str) -> tuple[int, list[str]]:
        deliveries = 0
        details: list[str] = []
        runs = self.control_plane.list_runs(status=status, source="email", limit=100)
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

    def _process_alert_notifications(self) -> tuple[int, list[str]]:
        deliveries = 0
        details: list[str] = []
        subscriptions = self.control_plane.list_subscriptions(
            channel="email",
            enabled=True,
            schedule_type="realtime",
            limit=200,
        )
        if not subscriptions:
            return deliveries, details

        lookback_cutoff = utcnow() - datetime.timedelta(hours=self.settings.alert_lookback_hours)

        open_alerts = [
            alert
            for alert in self.control_plane.list_alerts(status="open", scope_type="service_loop", limit=50)
            if (_parse_datetime(alert.get("detected_at")) or utcnow()) >= lookback_cutoff
        ]
        resolved_alerts = [
            alert
            for alert in self.control_plane.list_alerts(status="resolved", scope_type="service_loop", limit=50)
            if (
                _parse_datetime(alert.get("updated_at"))
                or _parse_datetime(alert.get("detected_at"))
                or utcnow()
            ) >= lookback_cutoff
        ]

        for alert in open_alerts:
            for subscription in subscriptions:
                if not self._matches_alert_subscription(alert, subscription):
                    continue
                dedup_key = f"alert-open:{alert['id']}:{subscription['id']}"
                if self._delivery_exists(dedup_key):
                    continue
                self._send_and_record(
                    to_address=str(subscription["target"]),
                    subject=_subject_alert(alert, resolved=False),
                    body=self._format_alert_body(alert, resolved=False),
                    thread_key=str(alert["id"]),
                    dedup_key=dedup_key,
                    message_type="alert_open",
                    related_alert_id=alert["id"],
                )
                deliveries += 1
                details.append(f"sent open alert email for alert {alert['id']} to {subscription['target']}")

        for alert in resolved_alerts:
            for subscription in subscriptions:
                if not self._matches_alert_subscription(alert, subscription):
                    continue
                open_dedup_key = f"alert-open:{alert['id']}:{subscription['id']}"
                resolved_dedup_key = f"alert-resolved:{alert['id']}:{subscription['id']}"
                if not self._delivery_exists(open_dedup_key) or self._delivery_exists(resolved_dedup_key):
                    continue
                self._send_and_record(
                    to_address=str(subscription["target"]),
                    subject=_subject_alert(alert, resolved=True),
                    body=self._format_alert_body(alert, resolved=True),
                    thread_key=str(alert["id"]),
                    dedup_key=resolved_dedup_key,
                    message_type="alert_resolved",
                    related_alert_id=alert["id"],
                )
                deliveries += 1
                details.append(f"sent resolved alert email for alert {alert['id']} to {subscription['target']}")

        return deliveries, details

    def _delivery_exists(self, dedup_key: str, *, delivery_status: str | None = "sent") -> bool:
        params: dict[str, Any] = {
            "connector": "email",
            "dedup_key": dedup_key,
            "limit": 1,
        }
        if delivery_status:
            params["delivery_status"] = delivery_status
        deliveries = self.control_plane.list_deliveries(**params)
        return bool(deliveries)

    def _read_state(self) -> dict[str, Any]:
        if not self.settings.state_path.exists():
            return {}
        try:
            return json.loads(self.settings.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_state(self, state: dict[str, Any]) -> None:
        self.settings.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        related_alert_id: str | None = None,
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
                    "related_alert_id": related_alert_id,
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
                    "related_alert_id": related_alert_id,
                    "failed_at": utcnow().isoformat(),
                }
            )
            raise

    @staticmethod
    def _matches_alert_subscription(alert: dict[str, Any], subscription: dict[str, Any]) -> bool:
        if str(subscription.get("channel") or "").strip().lower() != "email":
            return False
        if not subscription.get("enabled"):
            return False
        if not str(subscription.get("target") or "").strip():
            return False
        scope_type = str(subscription.get("scope_type") or "").strip()
        scope_id = str(subscription.get("scope_id") or "").strip()
        if scope_type and scope_type != str(alert.get("scope_type") or "").strip():
            return False
        if scope_id and scope_id != str(alert.get("scope_id") or "").strip():
            return False
        return _severity_value(alert.get("severity")) >= _severity_value(subscription.get("severity_floor"))

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

    @staticmethod
    def _format_alert_body(alert: dict[str, Any], *, resolved: bool) -> str:
        state = "resolved" if resolved else "open"
        evidence = str(alert.get("evidence_summary") or "").strip() or "No evidence summary available."
        scope_value = str(alert.get("scope_id") or alert.get("scope_type") or "global")
        return (
            f"Alert {alert['id']} is now {state}.\n\n"
            f"Summary: {alert.get('summary') or 'N/A'}\n"
            f"Severity: {alert.get('severity') or 'warning'}\n"
            f"Rule: {alert.get('source_rule') or 'N/A'}\n"
            f"Scope: {scope_value}\n"
            f"Detected at: {alert.get('detected_at') or 'N/A'}\n"
            f"Updated at: {alert.get('updated_at') or 'N/A'}\n\n"
            f"Evidence:\n{evidence}"
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
                received, received_details = self.service.process_inbound_once()
                created, details = self.service.process_outbound_once()
                if received:
                    print(f"[agent-email] processed inbound emails: {received}; details={received_details}")
                if created:
                    print(f"[agent-email] created deliveries: {created}; details={details}")
            except Exception as exc:
                print(f"[agent-email] background poll failed: {exc}")
