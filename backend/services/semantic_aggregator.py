from __future__ import annotations

from collections import Counter
from typing import Any


class SemanticWindowAggregator:
    def __init__(self, window_seconds: int = 30) -> None:
        self.window_seconds = max(5, int(window_seconds))

    def aggregate(self, frame_descriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not frame_descriptions:
            return []

        buckets: dict[int, list[dict[str, Any]]] = {}
        for item in frame_descriptions:
            timestamp = float(item.get("timestamp") or 0.0)
            start = int(timestamp // self.window_seconds) * self.window_seconds
            buckets.setdefault(start, []).append(item)

        summaries: list[dict[str, Any]] = []
        for start in sorted(buckets):
            items = buckets[start]
            end = start + self.window_seconds
            behavior_counter = Counter()
            risk_counter = Counter()
            people_samples: list[int] = []
            scene_fragments: list[str] = []

            for item in items:
                for behavior in item.get("behaviors") or []:
                    text = str(behavior).strip()
                    if text:
                        behavior_counter[text] += 1
                for risk in item.get("risk_signals") or []:
                    text = str(risk).strip()
                    if text:
                        risk_counter[text] += 1
                people = item.get("people_count_estimate")
                if isinstance(people, int):
                    people_samples.append(people)
                scene = str(item.get("scene_summary") or "").strip()
                if scene:
                    scene_fragments.append(scene)

            summaries.append(
                {
                    "window_start": start,
                    "window_end": end,
                    "window_summary": scene_fragments[0] if scene_fragments else "该时间窗口已完成语义抽取。",
                    "crowd_change": {
                        "average_people_count": round(sum(people_samples) / len(people_samples), 2)
                        if people_samples
                        else None,
                        "peak_people_count": max(people_samples) if people_samples else None,
                    },
                    "behavior_trends": [item for item, _count in behavior_counter.most_common(5)],
                    "anomaly_candidates": [item for item, _count in risk_counter.most_common(5)],
                    "evidence_timestamps": [entry.get("timestamp") for entry in items[:6]],
                    "frame_count": len(items),
                }
            )
        return summaries
