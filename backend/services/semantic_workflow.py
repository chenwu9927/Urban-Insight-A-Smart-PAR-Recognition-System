from __future__ import annotations

import os
from typing import Any

from .frame_sampler import FrameSampler
from .semantic_aggregator import SemanticWindowAggregator
from .video_analyst import VideoSemanticAnalyst
from .vlm_narrator import QwenFrameNarrator


class SemanticVideoWorkflow:
    def __init__(self) -> None:
        target_fps = float(os.getenv("SEMANTIC_VLM_SAMPLE_FPS", "1") or "1")
        max_frames = int(os.getenv("SEMANTIC_VLM_MAX_FRAMES", "180") or "180")
        window_seconds = int(os.getenv("SEMANTIC_VLM_WINDOW_SECONDS", "30") or "30")
        self.sampler = FrameSampler(default_fps=target_fps, max_frames=max_frames)
        self.narrator = QwenFrameNarrator()
        self.aggregator = SemanticWindowAggregator(window_seconds=window_seconds)
        self.analyst = VideoSemanticAnalyst()

    def analyze_video(
        self,
        file_path: str,
        *,
        camera_location: str = "Camera 01",
        progress_callback=None,
    ) -> dict[str, Any]:
        sampled = self.sampler.sample(file_path)
        frames = sampled["frames"]
        total = max(1, len(frames))
        descriptions: list[dict[str, Any]] = []

        for index, item in enumerate(frames, start=1):
            descriptions.append(
                self.narrator.describe_frame(
                    item["frame"],
                    timestamp=float(item.get("timestamp") or 0.0),
                    camera_location=camera_location,
                )
            )
            if progress_callback:
                try:
                    progress_callback(index, total)
                except Exception:
                    pass

        windows = self.aggregator.aggregate(descriptions)
        insights = self.analyst.summarize(
            frame_descriptions=descriptions,
            window_summaries=windows,
            duration=int(sampled.get("duration") or 0),
            camera_location=camera_location,
        )
        return {
            "frame_descriptions": descriptions,
            "window_summaries": windows,
            "video_insights": insights,
            "pipeline_meta": {
                "pipeline": "semantic_vlm",
                "sample_fps": sampled.get("sample_fps"),
                "source_fps": sampled.get("source_fps"),
                "sampled_frame_count": len(descriptions),
                "model": self.narrator.model,
                "vlm_enabled": self.narrator.enabled,
            },
            "duration": int(sampled.get("duration") or 0),
            "camera_location": camera_location,
        }
