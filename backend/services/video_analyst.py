from __future__ import annotations

from collections import Counter
from typing import Any


class VideoSemanticAnalyst:
    def summarize(
        self,
        *,
        frame_descriptions: list[dict[str, Any]],
        window_summaries: list[dict[str, Any]],
        duration: int,
        camera_location: str,
    ) -> dict[str, Any]:
        risk_counter = Counter()
        behavior_counter = Counter()

        for item in frame_descriptions:
            for risk in item.get("risk_signals") or []:
                text = str(risk).strip()
                if text:
                    risk_counter[text] += 1
            for behavior in item.get("behaviors") or []:
                text = str(behavior).strip()
                if text:
                    behavior_counter[text] += 1

        risk_items = [item for item, _count in risk_counter.most_common(5)]
        behavior_items = [item for item, _count in behavior_counter.most_common(5)]
        if risk_items:
            risk_level = "high" if len(risk_items) >= 3 else "medium"
            summary = f"视频中出现了需要关注的风险信号：{'、'.join(risk_items[:3])}。"
        elif behavior_items:
            risk_level = "low"
            summary = f"视频主要呈现以下行为趋势：{'、'.join(behavior_items[:3])}。"
        else:
            risk_level = "low"
            summary = "当前视频已完成语义分析，暂未提取出明显风险信号。"

        return {
            "camera_location": camera_location,
            "duration": duration,
            "risk_level": risk_level,
            "incident_summary": summary,
            "event_chain": [item.get("window_summary") for item in window_summaries[:8] if item.get("window_summary")],
            "operator_recommendations": (
                ["结合结构化结果复核关键片段", "必要时交给智能体继续追问"]
                if risk_items
                else ["可将本次摘要作为日常巡查记录归档"]
            ),
            "agent_followups": risk_items or behavior_items[:3],
        }
