from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from agent.connectors.email.schemas import (
    EmailInboundRequest,
    EmailInboundResponse,
    EmailProcessResponse,
    OutboxItemResponse,
)
from agent.connectors.email.service import EmailConnectorService

router = APIRouter()
service = EmailConnectorService()


@router.post("/email/inbound", response_model=EmailInboundResponse)
def email_inbound(payload: EmailInboundRequest):
    result, mode = service.ingest_email(payload.model_dump())
    if mode == "approval":
        return EmailInboundResponse(
            ok=True,
            mode=mode,
            approval_id=result["id"],
            detail=f"Approval {result['id']} answered with status {result['status']}",
        )

    return EmailInboundResponse(
        ok=True,
        mode=mode,
        session_id=result["session"]["id"],
        run_id=result["run"]["id"],
        detail="Email task accepted and converted to session/run",
    )


@router.post("/email/process-outbound", response_model=EmailProcessResponse)
def process_outbound():
    created, details = service.process_outbound_once()
    return EmailProcessResponse(ok=True, deliveries_created=created, details=details)


@router.get("/email/outbox", response_model=list[OutboxItemResponse])
def list_outbox():
    outbox = sorted(service.settings.outbox_dir.glob("*.json"), reverse=True)
    return [OutboxItemResponse(name=path.name, path=str(Path(path).resolve())) for path in outbox]
