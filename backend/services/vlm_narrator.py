from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from typing import Any

import cv2
from openai import OpenAI
from PIL import Image


def _extract_json_block(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    if "```json" in raw:
        fragment = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        candidates.insert(0, fragment)
    elif "```" in raw:
        fragment = raw.split("```", 1)[1].split("```", 1)[0].strip()
        candidates.insert(0, fragment)

    for candidate in candidates:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _frame_to_data_url(frame_bgr) -> str:
    image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


class QwenFrameNarrator:
    def __init__(self) -> None:
        self.api_base = (os.getenv("SEMANTIC_VLM_API_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()
        self.api_key = (os.getenv("SEMANTIC_VLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "EMPTY").strip()
        self.model = (os.getenv("SEMANTIC_VLM_MODEL") or "Qwen/Qwen3.5-0.8B").strip()
        self.enabled = bool(self.api_base)
        self.client = OpenAI(base_url=self.api_base, api_key=self.api_key) if self.enabled else None

    def describe_frame(self, frame_bgr, *, timestamp: float, camera_location: str = "Unknown") -> dict[str, Any]:
        if not self.enabled or self.client is None:
            return self._fallback_description(timestamp=timestamp, camera_location=camera_location)

        prompt = (
            "你是安防视频语义分析器。请只根据图片内容输出 JSON，不要输出解释文字。"
            "请不要猜测身份，不要虚构看不见的事实。"
            "返回字段必须包含：scene_summary, people_count_estimate, behaviors, risk_signals, environment_notes, confidence_notes。"
            "其中 behaviors 和 risk_signals 必须是字符串数组。"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _frame_to_data_url(frame_bgr)}},
                            {
                                "type": "text",
                                "text": (
                                    f"{prompt}\n"
                                    f"补充上下文：camera_location={camera_location}, timestamp={timestamp:.2f}s"
                                ),
                            },
                        ],
                    }
                ],
                temperature=0.3,
                top_p=0.8,
                extra_body={"top_k": 20},
            )
            content = response.choices[0].message.content if response.choices else ""
            if isinstance(content, list):
                text = "\n".join(
                    item.get("text", "").strip()
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                )
            else:
                text = str(content or "")
            parsed = _extract_json_block(text)
            if isinstance(parsed, dict):
                return self._normalize(parsed, timestamp=timestamp, camera_location=camera_location, source="qwen")
        except Exception:
            pass
        return self._fallback_description(timestamp=timestamp, camera_location=camera_location)

    def _normalize(
        self,
        payload: dict[str, Any],
        *,
        timestamp: float,
        camera_location: str,
        source: str,
    ) -> dict[str, Any]:
        people_count = payload.get("people_count_estimate")
        if not isinstance(people_count, int):
            try:
                people_count = int(people_count)
            except Exception:
                people_count = None
        return {
            "timestamp": round(float(timestamp), 2),
            "camera_location": camera_location,
            "scene_summary": str(payload.get("scene_summary") or "未生成场景摘要").strip(),
            "people_count_estimate": people_count,
            "pedestrian_descriptions": payload.get("pedestrian_descriptions") or [],
            "behaviors": [str(item).strip() for item in payload.get("behaviors") or [] if str(item).strip()],
            "risk_signals": [str(item).strip() for item in payload.get("risk_signals") or [] if str(item).strip()],
            "environment_notes": [str(item).strip() for item in payload.get("environment_notes") or [] if str(item).strip()],
            "confidence_notes": str(payload.get("confidence_notes") or "").strip(),
            "source": source,
        }

    def _fallback_description(self, *, timestamp: float, camera_location: str) -> dict[str, Any]:
        return {
            "timestamp": round(float(timestamp), 2),
            "camera_location": camera_location,
            "scene_summary": "当前帧已进入语义分析流程，但未配置在线多模态模型服务。",
            "people_count_estimate": None,
            "pedestrian_descriptions": [],
            "behaviors": [],
            "risk_signals": [],
            "environment_notes": ["可先用于打通第二工作流骨架。"],
            "confidence_notes": "fallback",
            "source": "fallback",
        }
