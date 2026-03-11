from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ExecuteRunRequest(BaseModel):
    claim: dict[str, Any]


class ExecuteRunResponse(BaseModel):
    output_payload: dict[str, Any]
    result_summary: str
    executor_mode: str = "api_only"
    error: Optional[str] = None
