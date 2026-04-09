from __future__ import annotations

import math
from typing import Any

import cv2


class FrameSampler:
    def __init__(self, default_fps: float = 1.0, max_frames: int = 180) -> None:
        self.default_fps = max(0.1, float(default_fps))
        self.max_frames = max(1, int(max_frames))

    def sample(self, file_path: str, *, target_fps: float | None = None) -> dict[str, Any]:
        capture = cv2.VideoCapture(file_path)
        if not capture.isOpened():
            raise RuntimeError(f"Unable to open video: {file_path}")

        try:
            source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = int(round(frame_count / source_fps)) if source_fps > 0 and frame_count > 0 else 0
            sample_fps = max(0.1, float(target_fps or self.default_fps))

            if source_fps <= 0:
                source_fps = max(sample_fps, 1.0)

            frame_step = max(1, int(math.floor(source_fps / sample_fps)))
            sampled: list[dict[str, Any]] = []
            frame_index = 0

            while len(sampled) < self.max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % frame_step == 0:
                    timestamp = round(frame_index / source_fps, 2)
                    sampled.append(
                        {
                            "frame_index": frame_index,
                            "timestamp": timestamp,
                            "frame": frame,
                        }
                    )
                frame_index += 1

            return {
                "source_fps": source_fps,
                "sample_fps": sample_fps,
                "frame_count": frame_count,
                "duration": duration,
                "frames": sampled,
            }
        finally:
            capture.release()
