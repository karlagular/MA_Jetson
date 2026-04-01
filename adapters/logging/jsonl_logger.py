"""JSONL event logger + frame save + latency CSV export."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import List

import cv2
import numpy as np

from domain.models import AlarmEvent
from ports.logger import EventLoggerPort


class JsonlLogger(EventLoggerPort):
    def __init__(self, session_dir: str) -> None:
        self._dir = session_dir
        os.makedirs(self._dir, exist_ok=True)
        self._events_path = os.path.join(self._dir, "events.jsonl")

    def log_alarm(self, event: AlarmEvent) -> None:
        with open(self._events_path, "a") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

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
