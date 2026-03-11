from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent.executor.schemas import ExecuteRunRequest, ExecuteRunResponse
from agent.executor.service import ApiOnlyExecutionService

router = APIRouter()
service = ApiOnlyExecutionService()


@router.post("/execute", response_model=ExecuteRunResponse)
def execute_run(payload: ExecuteRunRequest):
    try:
        output_payload, result_summary = service.execute(payload.claim)
        return ExecuteRunResponse(
            output_payload=output_payload,
            result_summary=result_summary,
            executor_mode="api_only",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
