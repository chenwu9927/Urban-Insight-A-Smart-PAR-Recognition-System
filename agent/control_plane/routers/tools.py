from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from agent.control_plane.schemas import AgentToolResponse
from agent.tool_registry import get_tool_spec, list_tool_specs

router = APIRouter()


@router.get("/agent/tools", response_model=list[AgentToolResponse])
def list_agent_tools(
    category: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    approval_mode: str | None = Query(default=None),
):
    specs = list_tool_specs()
    if category:
        specs = [spec for spec in specs if spec.category == category]
    if risk_level:
        specs = [spec for spec in specs if spec.risk_level == risk_level]
    if approval_mode:
        specs = [spec for spec in specs if spec.approval_mode == approval_mode]
    return [AgentToolResponse.model_validate(spec.to_dict()) for spec in specs]


@router.get("/agent/tools/{action}", response_model=AgentToolResponse)
def get_agent_tool(action: str):
    spec = get_tool_spec(action)
    if spec is None:
        raise HTTPException(status_code=404, detail="Agent tool not found")
    return AgentToolResponse.model_validate(spec.to_dict())
