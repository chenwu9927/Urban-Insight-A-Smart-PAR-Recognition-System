from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from agent.tool_registry import AgentToolParameter, AgentToolSpec


def _chat_completions_url(base_url: str) -> str:
    normalized = (base_url or "https://api.openai.com/v1").rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    if normalized.endswith("/openai"):
        return f"{normalized}/v1/chat/completions"
    return f"{normalized}/chat/completions"


def _post_json(url: str, *, headers: dict[str, str], payload: dict[str, Any], timeout_s: int = 45) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _json_schema_type(value_type: str) -> str:
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "object": "object",
        "array": "array",
    }
    return mapping.get((value_type or "").strip().lower(), "string")


def _parameter_schema(parameter: AgentToolParameter) -> dict[str, Any]:
    schema_type = _json_schema_type(parameter.value_type)
    schema: dict[str, Any] = {
        "type": schema_type,
        "description": parameter.description,
    }
    if parameter.default is not None:
        schema["default"] = parameter.default
    if schema_type == "object":
        schema["additionalProperties"] = True
    return schema


def build_openai_tool_definition(spec: AgentToolSpec) -> dict[str, Any]:
    properties = {
        item.name: _parameter_schema(item)
        for item in spec.input_parameters
    }
    required = [item.name for item in spec.input_parameters if item.required]
    return {
        "type": "function",
        "function": {
            "name": spec.action,
            "description": spec.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


@dataclass
class ToolLoopResult:
    answer: str
    iterations: int
    tool_events: list[dict[str, Any]]
    raw_messages: list[dict[str, Any]]


class OpenAICompatibleToolLoopClient:
    def __init__(self, *, timeout_seconds: int = 45) -> None:
        self.timeout_seconds = max(10, int(timeout_seconds))

    def is_configured(self) -> bool:
        return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY not configured")

        base_url = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        model = os.getenv("LLM_MODEL") or "gpt-4o-mini"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        return _post_json(
            _chat_completions_url(base_url),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload=payload,
            timeout_s=self.timeout_seconds,
        )


class ToolLoopRunner:
    def __init__(
        self,
        *,
        llm_client: OpenAICompatibleToolLoopClient | None = None,
        max_iterations: int = 6,
    ) -> None:
        self.llm_client = llm_client or OpenAICompatibleToolLoopClient()
        self.max_iterations = max(1, int(max_iterations))

    def run(
        self,
        *,
        system_prompt: str,
        conversation_messages: list[dict[str, Any]],
        available_tools: list[AgentToolSpec],
        execute_tool: Callable[[str, dict[str, Any]], tuple[dict[str, Any], str]],
        max_iterations: int | None = None,
    ) -> ToolLoopResult:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_messages)
        tool_defs = [build_openai_tool_definition(spec) for spec in available_tools]
        tool_events: list[dict[str, Any]] = []
        iteration_budget = max(1, int(max_iterations or self.max_iterations))

        for iteration in range(1, iteration_budget + 1):
            response = self.llm_client.complete(messages=messages, tools=tool_defs)
            choice = ((response.get("choices") or [{}])[0] or {})
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            content = message.get("content")
            assistant_content = self._stringify_content(content)

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_content,
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)

            if not tool_calls:
                final_answer = assistant_content.strip() or "Agent completed the turn without a textual response."
                return ToolLoopResult(
                    answer=final_answer,
                    iterations=iteration,
                    tool_events=tool_events,
                    raw_messages=messages,
                )

            for tool_call in tool_calls:
                function_payload = tool_call.get("function") or {}
                action = str(function_payload.get("name") or "").strip()
                arguments = self._parse_arguments(function_payload.get("arguments"))
                try:
                    output_payload, result_summary = execute_tool(action, arguments)
                    tool_result = {
                        "ok": True,
                        "action": action,
                        "result_summary": result_summary,
                        "output_payload": output_payload,
                    }
                except Exception as exc:  # pragma: no cover - exercised in runtime, not unit smoke
                    tool_result = {
                        "ok": False,
                        "action": action,
                        "error": str(exc),
                    }
                tool_events.append(tool_result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

        return ToolLoopResult(
            answer="Agent reached the tool iteration limit before producing a final answer.",
            iterations=iteration_budget,
            tool_events=tool_events,
            raw_messages=messages,
        )

    @staticmethod
    def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return dict(raw_arguments)
        if isinstance(raw_arguments, str) and raw_arguments.strip():
            try:
                parsed = json.loads(raw_arguments)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _stringify_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts)
        return ""
