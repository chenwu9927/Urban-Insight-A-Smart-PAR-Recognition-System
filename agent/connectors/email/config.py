from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class EmailConnectorSettings:
    def __init__(self) -> None:
        self.control_plane_url = os.getenv("AGENT_CONTROL_PLANE_URL", "http://agent-control-plane:8000").rstrip("/")
        self.delivery_mode = os.getenv("AGENT_EMAIL_DELIVERY_MODE", "log").strip().lower() or "log"
        self.outbox_dir = Path(os.getenv("AGENT_EMAIL_OUTBOX_DIR", "agent_email_outbox"))
        self.default_from_address = os.getenv("AGENT_EMAIL_FROM_ADDRESS", "agent@urban-insight.local").strip()
        self.poll_seconds = max(5, _env_int("AGENT_EMAIL_POLL_SECONDS", 10))
        self.enable_background = _env_bool("AGENT_EMAIL_ENABLE_BACKGROUND", False)
        self.smtp_host = os.getenv("AGENT_EMAIL_SMTP_HOST", "").strip()
        self.smtp_port = _env_int("AGENT_EMAIL_SMTP_PORT", 587)
        self.smtp_username = os.getenv("AGENT_EMAIL_SMTP_USERNAME", "").strip()
        self.smtp_password = os.getenv("AGENT_EMAIL_SMTP_PASSWORD", "").strip()
        self.smtp_use_tls = _env_bool("AGENT_EMAIL_SMTP_USE_TLS", True)
        self.imap_enable = _env_bool("AGENT_EMAIL_IMAP_ENABLE", False)
        self.imap_host = os.getenv("AGENT_EMAIL_IMAP_HOST", "").strip()
        self.imap_port = _env_int("AGENT_EMAIL_IMAP_PORT", 993)
        self.imap_username = os.getenv("AGENT_EMAIL_IMAP_USERNAME", "").strip()
        self.imap_password = os.getenv("AGENT_EMAIL_IMAP_PASSWORD", "").strip()
        self.imap_use_ssl = _env_bool("AGENT_EMAIL_IMAP_USE_SSL", True)
        self.imap_mailbox = os.getenv("AGENT_EMAIL_IMAP_MAILBOX", "INBOX").strip() or "INBOX"
        self.state_path = Path(os.getenv("AGENT_EMAIL_STATE_PATH", "agent_email_state/imap-state.json"))
