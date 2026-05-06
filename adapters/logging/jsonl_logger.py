"""JSONL event logger + frame save + latency CSV export."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import List

import cv2
import numpy as np

from domain.models import AlarmEvent, BBox
from ports.logger import EventLoggerPort


class JsonlLogger(EventLoggerPort):
    def __init__(
        self,
        session_dir: str,
        alarm_m: int | None = None,
        alarm_n: int | None = None,
        alarm_disappear_frames: int | None = None,
        inference_conf: float | None = None,
    ) -> None:
        self._dir = session_dir
        os.makedirs(self._dir, exist_ok=True)
        self._events_path = os.path.join(self._dir, "events.jsonl")
        self._started_at = datetime.now()
        self._alarms_activated = 0
        self._alarm_m = alarm_m
        self._alarm_n = alarm_n
        self._alarm_disappear_frames = alarm_disappear_frames
        self._inference_conf = inference_conf

    def log_alarm(self, event: AlarmEvent) -> None:
        with open(self._events_path, "a") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        if event.state_to == "ALARMED":
            self._alarms_activated += 1

    def save_frame(self, frame: np.ndarray, label: str) -> None:
        path = os.path.join(self._dir, f"{label}.jpg")
        cv2.imwrite(path, frame)
        print(f"[Logger] Frame saved to {path}")

    def save_latency_log(self, records: List[tuple]) -> None:
        path = os.path.join(self._dir, "latency_log.txt")
        header = "frame,capture_ms,inference_ms,postprocess_ms,policy_ms,display_ms,total_ms"
        with open(path, "w") as f:
            f.write(header + "\n")
            for r in records:
                f.write(",".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in r) + "\n")
        print(f"[Logger] Latency log saved to {path}")

    def save_bboxes(self, boxes: List[BBox], label: str) -> None:
        path = os.path.join(self._dir, f"{label}.json")
        payload = [asdict(box) for box in boxes]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[Logger] BBoxes saved to {path}")

    def save_run_summary(
        self,
        frame_count: int,
        alarms_activated: int | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        started = started_at or self._started_at
        ended = ended_at or datetime.now()
        summary = {
            "started_at": started.isoformat(timespec="seconds"),
            "ended_at": ended.isoformat(timespec="seconds"),
            "frame_count": int(frame_count),
            "alarms_activated": int(self._alarms_activated if alarms_activated is None else alarms_activated),
            "alarm_m": self._alarm_m,
            "alarm_n": self._alarm_n,
            "alarm_disappear_frames": self._alarm_disappear_frames,
            "inference_conf": self._inference_conf,
            "run_dir": self._dir,
        }
        path = os.path.join(self._dir, "summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"[Logger] Summary saved to {path}")
