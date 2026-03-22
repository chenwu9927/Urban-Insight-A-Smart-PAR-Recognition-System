from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import AgentAlertResponse
from agent.models import AgentAlert
from backend.database import get_db

router = APIRouter()


@router.get("/agent/alerts", response_model=list[AgentAlertResponse])
def list_agent_alerts(
    status: str | None = None,
    severity: str | None = None,
    source_rule: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentAlert)
    if status:
        query = query.filter(AgentAlert.status == status)
    if severity:
        query = query.filter(AgentAlert.severity == severity)
    if source_rule:
        query = query.filter(AgentAlert.source_rule == source_rule)
    if scope_type:
        query = query.filter(AgentAlert.scope_type == scope_type)
    if scope_id:
        query = query.filter(AgentAlert.scope_id == scope_id)
    if status == "resolved":
        return query.order_by(AgentAlert.updated_at.desc(), AgentAlert.created_at.desc()).limit(limit).all()
    return query.order_by(AgentAlert.detected_at.desc(), AgentAlert.created_at.desc()).limit(limit).all()


@router.get("/agent/alerts/{alert_id}", response_model=AgentAlertResponse)
def get_agent_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(AgentAlert).filter(AgentAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Agent alert not found")
    return alert
