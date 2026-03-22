from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentConnectorDeliveryCreate,
    AgentConnectorDeliveryResponse,
)
from agent.models import AgentConnectorDelivery
from backend.database import get_db

router = APIRouter()


@router.get("/agent/deliveries", response_model=list[AgentConnectorDeliveryResponse])
def list_deliveries(
    connector: str | None = None,
    delivery_status: str | None = None,
    related_run_id: str | None = None,
    related_alert_id: str | None = None,
    dedup_key: str | None = None,
    target_address: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AgentConnectorDelivery)
    if connector:
        query = query.filter(AgentConnectorDelivery.connector == connector)
    if delivery_status:
        query = query.filter(AgentConnectorDelivery.delivery_status == delivery_status)
    if related_run_id:
        query = query.filter(AgentConnectorDelivery.related_run_id == related_run_id)
    if related_alert_id:
        query = query.filter(AgentConnectorDelivery.related_alert_id == related_alert_id)
    if dedup_key:
        query = query.filter(AgentConnectorDelivery.dedup_key == dedup_key)
    if target_address:
        query = query.filter(AgentConnectorDelivery.target_address == target_address)
    return query.order_by(AgentConnectorDelivery.created_at.desc()).limit(limit).all()


@router.post("/agent/deliveries", response_model=AgentConnectorDeliveryResponse)
def create_delivery(payload: AgentConnectorDeliveryCreate, db: Session = Depends(get_db)):
    delivery = AgentConnectorDelivery(**payload.model_dump())
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery
