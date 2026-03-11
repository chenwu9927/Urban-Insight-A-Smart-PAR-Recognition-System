from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentSessionCreate(BaseModel):
    kind: str = "command"
    title: Optional[str] = None
    status: str = "active"
    owner_user_id: Optional[int] = None
    site_id: Optional[str] = None
    camera_id: Optional[str] = None
    source: str = "manual"
    config_snapshot: Optional[dict[str, Any]] = None
    state_patch: Optional[dict[str, Any]] = None


class AgentSessionResponse(BaseModel):
    id: str
    kind: str
    title: Optional[str] = None
    status: str
    owner_user_id: Optional[int] = None
    site_id: Optional[str] = None
    camera_id: Optional[str] = None
    source: str
    config_snapshot: Optional[dict[str, Any]] = None
    state_patch: Optional[dict[str, Any]] = None
    last_run_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AgentMessageCreate(BaseModel):
    role: str
    content: dict[str, Any]
    text_preview: Optional[str] = None
    connector: Optional[str] = None
    connector_message_id: Optional[str] = None
    thread_key: Optional[str] = None


class AgentMessageResponse(BaseModel):
    id: str
    session_id: str
    run_id: Optional[str] = None
    role: str
    content: dict[str, Any]
    text_preview: Optional[str] = None
    connector: Optional[str] = None
    connector_message_id: Optional[str] = None
    thread_key: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AgentRunCreate(BaseModel):
    session_id: str
    trigger_message_id: Optional[str] = None
    created_by_user_id: Optional[int] = None
    schedule_mode: str = "immediate"
    permission_mode: str = "default"
    config_snapshot: Optional[dict[str, Any]] = None
    input_payload: Optional[dict[str, Any]] = None
    prompt: Optional[str] = None
    scheduled_at: Optional[datetime.datetime] = None


class AgentRunResponse(BaseModel):
    id: str
    session_id: str
    trigger_message_id: Optional[str] = None
    scheduled_task_id: Optional[str] = None
    created_by_user_id: Optional[int] = None
    status: str
    schedule_mode: str
    permission_mode: str
    progress: int
    config_snapshot: Optional[dict[str, Any]] = None
    input_payload: Optional[dict[str, Any]] = None
    output_payload: Optional[dict[str, Any]] = None
    result_summary: Optional[str] = None
    scheduled_at: datetime.datetime
    claimed_by: Optional[str] = None
    lease_expires_at: Optional[datetime.datetime] = None
    last_heartbeat_at: Optional[datetime.datetime] = None
    attempts: int
    last_error: Optional[str] = None
    started_at: Optional[datetime.datetime] = None
    finished_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AgentRunClaimRequest(BaseModel):
    worker_id: str
    lease_seconds: int = 60
    schedule_modes: list[str] = Field(default_factory=list)


class AgentRunClaimResponse(BaseModel):
    claimed: bool
    run: Optional[AgentRunResponse] = None
    trigger_message: Optional[AgentMessageResponse] = None
    session: Optional[AgentSessionResponse] = None


class AgentRunHeartbeatRequest(BaseModel):
    worker_id: str
    lease_seconds: int = 60
    progress: Optional[int] = None


class AgentRunCompleteRequest(BaseModel):
    worker_id: Optional[str] = None
    output_payload: Optional[dict[str, Any]] = None
    result_summary: Optional[str] = None


class AgentRunFailRequest(BaseModel):
    worker_id: Optional[str] = None
    error_message: str


class AgentScheduledTaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    reuse_session: bool = True
    session_id: Optional[str] = None
    created_by_user_id: Optional[int] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    cron: str
    timezone: str = "Asia/Shanghai"
    prompt_template: str
    risk_profile: str = "normal"
    config_snapshot: Optional[dict[str, Any]] = None
    next_run_at: Optional[datetime.datetime] = None
    cooldown_minutes: int = 0
    dedup_window_minutes: int = 0


class AgentScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    reuse_session: Optional[bool] = None
    session_id: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    cron: Optional[str] = None
    timezone: Optional[str] = None
    prompt_template: Optional[str] = None
    risk_profile: Optional[str] = None
    config_snapshot: Optional[dict[str, Any]] = None
    next_run_at: Optional[datetime.datetime] = None
    cooldown_minutes: Optional[int] = None
    dedup_window_minutes: Optional[int] = None


class AgentScheduledTaskResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    enabled: bool
    reuse_session: bool
    session_id: Optional[str] = None
    created_by_user_id: Optional[int] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    cron: str
    timezone: str
    prompt_template: str
    risk_profile: str
    config_snapshot: Optional[dict[str, Any]] = None
    next_run_at: datetime.datetime
    cooldown_minutes: int
    dedup_window_minutes: int
    last_run_id: Optional[str] = None
    last_run_status: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AgentScheduledTaskTriggerResponse(BaseModel):
    task_id: str
    session_id: str
    run_id: str


class AgentScheduledTaskDispatchResponse(BaseModel):
    dispatched: int
    skipped: int
    run_ids: list[str]


class AgentApprovalRequestCreate(BaseModel):
    run_id: str
    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    risk_level: str = "R3"
    reason: Optional[str] = None
    expires_at: Optional[datetime.datetime] = None


class AgentApprovalRequestAnswer(BaseModel):
    answered_by_user_id: Optional[int] = None
    status: str
    answers: Optional[dict[str, Any]] = None


class AgentApprovalRequestResponse(BaseModel):
    id: str
    run_id: str
    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    risk_level: str
    reason: Optional[str] = None
    status: str
    answers: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime.datetime] = None
    answered_by_user_id: Optional[int] = None
    answered_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class AgentConnectorDeliveryCreate(BaseModel):
    connector: str
    direction: str
    message_type: str
    delivery_status: str = "queued"
    dedup_key: Optional[str] = None
    thread_key: Optional[str] = None
    source_address: Optional[str] = None
    target_address: Optional[str] = None
    subject: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    related_run_id: Optional[str] = None
    related_alert_id: Optional[str] = None
    sent_at: Optional[datetime.datetime] = None
    failed_at: Optional[datetime.datetime] = None


class AgentConnectorDeliveryResponse(BaseModel):
    id: str
    connector: str
    direction: str
    thread_key: Optional[str] = None
    message_type: str
    delivery_status: str
    dedup_key: Optional[str] = None
    source_address: Optional[str] = None
    target_address: Optional[str] = None
    subject: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    related_run_id: Optional[str] = None
    related_alert_id: Optional[str] = None
    sent_at: Optional[datetime.datetime] = None
    failed_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}
