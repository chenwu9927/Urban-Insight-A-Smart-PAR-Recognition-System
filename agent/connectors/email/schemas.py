from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class EmailInboundRequest(BaseModel):
    from_address: str
    subject: str
    text: str = ""
    thread_key: Optional[str] = None
    connector_message_id: Optional[str] = None
    session_id: Optional[str] = None
    action: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    approval_id: Optional[str] = None
    decision: Optional[str] = None
    answers: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmailInboundResponse(BaseModel):
    ok: bool
    mode: str
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    approval_id: Optional[str] = None
    detail: str


class EmailProcessResponse(BaseModel):
    ok: bool
    deliveries_created: int
    details: list[str]


class OutboxItemResponse(BaseModel):
    name: str
    path: str
