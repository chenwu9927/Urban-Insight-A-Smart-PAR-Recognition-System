import datetime
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from backend.database import Base


def utcnow():
    return datetime.datetime.utcnow()


def uuid_str():
    return str(uuid.uuid4())


class TimestampMixin:
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class AgentSession(Base, TimestampMixin):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_kind_status", "kind", "status"),
        Index("ix_agent_sessions_scope", "site_id", "camera_id"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    kind = Column(String(50), default="command", nullable=False, index=True)
    title = Column(String(255), nullable=True)
    status = Column(String(50), default="active", nullable=False, index=True)
    owner_user_id = Column(Integer, nullable=True, index=True)
    site_id = Column(String(100), nullable=True, index=True)
    camera_id = Column(String(100), nullable=True, index=True)
    source = Column(String(50), default="manual", nullable=False)
    config_snapshot = Column(JSON, nullable=True)
    state_patch = Column(JSON, nullable=True)
    last_run_at = Column(DateTime, nullable=True, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)


class AgentMessage(Base, TimestampMixin):
    __tablename__ = "agent_messages"
    __table_args__ = (
        Index("ix_agent_messages_session_role_created", "session_id", "role", "created_at"),
        Index("ix_agent_messages_connector_message", "connector", "connector_message_id"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    session_id = Column(String(36), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    role = Column(String(50), nullable=False, index=True)
    content = Column(JSON, nullable=False)
    text_preview = Column(String(500), nullable=True)
    connector = Column(String(50), nullable=True, index=True)
    connector_message_id = Column(String(255), nullable=True, index=True)
    thread_key = Column(String(255), nullable=True, index=True)


class AgentGoal(Base, TimestampMixin):
    __tablename__ = "agent_goals"
    __table_args__ = (
        Index("ix_agent_goals_status_updated", "status", "updated_at"),
        Index("ix_agent_goals_session_status", "session_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    session_id = Column(String(36), nullable=False, index=True)
    root_run_id = Column(String(36), nullable=False, index=True)
    latest_run_id = Column(String(36), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    status = Column(String(50), default="planned", nullable=False, index=True)
    auto_replan = Column(Boolean, default=True, nullable=False)
    step_count = Column(Integer, default=0, nullable=False)
    active_steps = Column(Integer, default=0, nullable=False)
    completed_steps = Column(Integer, default=0, nullable=False)
    failed_steps = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    last_planned_at = Column(DateTime, nullable=True, index=True)
    last_replanned_at = Column(DateTime, nullable=True, index=True)
    meta = Column(JSON, nullable=True)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_status_scheduled", "status", "scheduled_at", "created_at"),
        Index("ix_agent_runs_session_status", "session_id", "status"),
        Index("ix_agent_runs_claim", "claimed_by", "lease_expires_at"),
        Index("ix_agent_runs_parent_goal_step", "parent_run_id", "goal_key", "step_index"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    session_id = Column(String(36), nullable=False, index=True)
    trigger_message_id = Column(String(36), nullable=True, index=True)
    scheduled_task_id = Column(String(36), nullable=True, index=True)
    parent_run_id = Column(String(36), nullable=True, index=True)
    goal_key = Column(String(255), nullable=True, index=True)
    step_index = Column(Integer, nullable=True, index=True)
    created_by_user_id = Column(Integer, nullable=True, index=True)
    status = Column(String(50), default="queued", nullable=False, index=True)
    schedule_mode = Column(String(50), default="immediate", nullable=False, index=True)
    permission_mode = Column(String(50), default="default", nullable=False, index=True)
    progress = Column(Integer, default=0, nullable=False)
    config_snapshot = Column(JSON, nullable=True)
    input_payload = Column(JSON, nullable=True)
    output_payload = Column(JSON, nullable=True)
    result_summary = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    claimed_by = Column(String(255), nullable=True, index=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    last_heartbeat_at = Column(DateTime, nullable=True, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)


class AgentScheduledTask(Base, TimestampMixin):
    __tablename__ = "agent_scheduled_tasks"
    __table_args__ = (
        Index("ix_agent_scheduled_tasks_enabled_next", "enabled", "next_run_at"),
        Index("ix_agent_scheduled_tasks_scope", "scope_type", "scope_id"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False, index=True)
    reuse_session = Column(Boolean, default=True, nullable=False)
    session_id = Column(String(36), nullable=True, index=True)
    created_by_user_id = Column(Integer, nullable=True, index=True)
    scope_type = Column(String(50), nullable=True, index=True)
    scope_id = Column(String(100), nullable=True, index=True)
    cron = Column(String(100), nullable=False)
    timezone = Column(String(64), default="Asia/Shanghai", nullable=False)
    prompt_template = Column(Text, nullable=False)
    risk_profile = Column(String(50), default="normal", nullable=False)
    config_snapshot = Column(JSON, nullable=True)
    next_run_at = Column(DateTime, nullable=False, index=True)
    cooldown_minutes = Column(Integer, default=0, nullable=False)
    dedup_window_minutes = Column(Integer, default=0, nullable=False)
    last_run_id = Column(String(36), nullable=True, index=True)
    last_run_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)


class AgentApprovalRequest(Base, TimestampMixin):
    __tablename__ = "agent_approval_requests"
    __table_args__ = (
        Index("ix_agent_approval_requests_status_expires", "status", "expires_at"),
        Index("ix_agent_approval_requests_run_status", "run_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(36), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    tool_input = Column(JSON, nullable=False)
    risk_level = Column(String(10), default="R3", nullable=False, index=True)
    reason = Column(Text, nullable=True)
    status = Column(String(50), default="pending", nullable=False, index=True)
    answers = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    answered_by_user_id = Column(Integer, nullable=True, index=True)
    answered_at = Column(DateTime, nullable=True, index=True)


class AgentIncident(Base, TimestampMixin):
    __tablename__ = "agent_incidents"
    __table_args__ = (
        Index("ix_agent_incidents_status_severity", "status", "severity"),
        Index("ix_agent_incidents_scope", "scope_type", "scope_id"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    scope_type = Column(String(50), nullable=True, index=True)
    scope_id = Column(String(100), nullable=True, index=True)
    severity = Column(String(20), default="warning", nullable=False, index=True)
    status = Column(String(50), default="open", nullable=False, index=True)
    owner_user_id = Column(Integer, nullable=True, index=True)
    playbook_version = Column(String(50), nullable=True)
    first_seen_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    last_seen_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    ack_at = Column(DateTime, nullable=True, index=True)
    resolved_at = Column(DateTime, nullable=True, index=True)


class AgentAlert(Base, TimestampMixin):
    __tablename__ = "agent_alerts"
    __table_args__ = (
        Index("ix_agent_alerts_status_severity", "status", "severity"),
        Index("ix_agent_alerts_dedup_detected", "dedup_key", "detected_at"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    incident_id = Column(String(36), nullable=True, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    source_rule = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), default="warning", nullable=False, index=True)
    status = Column(String(50), default="open", nullable=False, index=True)
    dedup_key = Column(String(255), nullable=False, index=True)
    summary = Column(String(500), nullable=False)
    evidence_summary = Column(Text, nullable=True)
    scope_type = Column(String(50), nullable=True, index=True)
    scope_id = Column(String(100), nullable=True, index=True)
    detected_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    notified_at = Column(DateTime, nullable=True, index=True)


class AgentSubscription(Base, TimestampMixin):
    __tablename__ = "agent_subscriptions"
    __table_args__ = (
        Index("ix_agent_subscriptions_scope", "scope_type", "scope_id"),
        Index("ix_agent_subscriptions_channel_target", "channel", "target"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    user_id = Column(Integer, nullable=True, index=True)
    channel = Column(String(50), nullable=False, index=True)
    target = Column(String(255), nullable=False, index=True)
    scope_type = Column(String(50), nullable=True, index=True)
    scope_id = Column(String(100), nullable=True, index=True)
    severity_floor = Column(String(20), default="warning", nullable=False)
    schedule_type = Column(String(50), default="realtime", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False, index=True)


class AgentArtifact(Base, TimestampMixin):
    __tablename__ = "agent_artifacts"
    __table_args__ = (
        Index("ix_agent_artifacts_run_type", "run_id", "artifact_type"),
        Index("ix_agent_artifacts_incident_type", "incident_id", "artifact_type"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(36), nullable=True, index=True)
    incident_id = Column(String(36), nullable=True, index=True)
    artifact_type = Column(String(50), nullable=False, index=True)
    storage_key = Column(String(500), nullable=False, index=True)
    mime_type = Column(String(100), nullable=True)
    checksum = Column(String(128), nullable=True)
    size_bytes = Column(Integer, default=0, nullable=False)
    details = Column(JSON, nullable=True)


class AgentMemoryItem(Base, TimestampMixin):
    __tablename__ = "agent_memory_items"
    __table_args__ = (
        Index("ix_agent_memory_items_scope", "scope_type", "scope_id"),
        Index("ix_agent_memory_items_type_approved", "memory_type", "approved"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    memory_type = Column(String(50), nullable=False, index=True)
    scope_type = Column(String(50), nullable=False, index=True)
    scope_id = Column(String(100), nullable=False, index=True)
    content = Column(Text, nullable=False)
    summary = Column(String(500), nullable=True)
    source_ref = Column(String(255), nullable=True, index=True)
    confidence = Column(Float, default=0.5, nullable=False)
    sensitivity = Column(String(20), default="normal", nullable=False)
    approved = Column(Boolean, default=False, nullable=False, index=True)
    ttl_at = Column(DateTime, nullable=True, index=True)
    superseded_by = Column(String(36), nullable=True, index=True)
    created_by_run_id = Column(String(36), nullable=True, index=True)
    extra = Column(JSON, nullable=True)


class AgentMemoryJob(Base, TimestampMixin):
    __tablename__ = "agent_memory_jobs"
    __table_args__ = (
        Index("ix_agent_memory_jobs_status_created", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(36), nullable=True, index=True)
    status = Column(String(50), default="queued", nullable=False, index=True)
    progress = Column(Integer, default=0, nullable=False)
    input_payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)


class AgentConnectorDelivery(Base, TimestampMixin):
    __tablename__ = "agent_connector_deliveries"
    __table_args__ = (
        Index("ix_agent_connector_deliveries_status", "connector", "delivery_status"),
        Index("ix_agent_connector_deliveries_dedup", "dedup_key", "delivery_status"),
    )

    id = Column(String(36), primary_key=True, default=uuid_str)
    connector = Column(String(50), nullable=False, index=True)
    direction = Column(String(20), nullable=False, index=True)
    thread_key = Column(String(255), nullable=True, index=True)
    message_type = Column(String(50), nullable=False, index=True)
    delivery_status = Column(String(50), default="queued", nullable=False, index=True)
    dedup_key = Column(String(255), nullable=True, index=True)
    source_address = Column(String(255), nullable=True)
    target_address = Column(String(255), nullable=True, index=True)
    subject = Column(String(500), nullable=True)
    payload = Column(JSON, nullable=True)
    related_run_id = Column(String(36), nullable=True, index=True)
    related_alert_id = Column(String(36), nullable=True, index=True)
    sent_at = Column(DateTime, nullable=True, index=True)
    failed_at = Column(DateTime, nullable=True, index=True)


class AgentDedupEvent(Base):
    __tablename__ = "agent_dedup_events"

    key = Column(String(255), primary_key=True)
    category = Column(String(50), nullable=False, index=True)
    scope = Column(String(100), nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)


AGENT_MODEL_TABLES = (
    AgentSession.__table__,
    AgentMessage.__table__,
    AgentGoal.__table__,
    AgentRun.__table__,
    AgentScheduledTask.__table__,
    AgentApprovalRequest.__table__,
    AgentIncident.__table__,
    AgentAlert.__table__,
    AgentSubscription.__table__,
    AgentArtifact.__table__,
    AgentMemoryItem.__table__,
    AgentMemoryJob.__table__,
    AgentConnectorDelivery.__table__,
    AgentDedupEvent.__table__,
)

AGENT_TABLE_NAMES = tuple(table.name for table in AGENT_MODEL_TABLES)
