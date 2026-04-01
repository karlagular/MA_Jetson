"""LatencyTracker — ring-buffer statistics and CSV export.

Moved from the old RunwithUI.py, now parameterised with a ClockPort
and expanded to 6 measurement stages.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import List, Optional

import numpy as np

from ports.clock import ClockPort

_HEADER = "frame,capture_ms,inference_ms,postprocess_ms,policy_ms,display_ms,total_ms"


class LatencyTracker:
    def __init__(
        self,
        clock: ClockPort,
        window_size: int = 60,
        session_id: Optional[str] = None,
    ) -> None:
        self._clock = clock
        self._records: List[tuple] = []
        self._frame_index = 0
        self._lock = threading.Lock()
        self._window_size = window_size
        self._session_timestamp = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._stop_event = threading.Event()
        self._print_thread = threading.Thread(target=self._print_loop, daemon=True)
        self._print_thread.start()

    # ------------------------------------------------------------------
    def record(
        self,
        capture_ms: float,
        inference_ms: float,
        postprocess_ms: float,
        policy_ms: float,
        display_ms: float,
        total_ms: float,
    ) -> None:
        entry = (
            self._frame_index,
            capture_ms,
            inference_ms,
            postprocess_ms,
            policy_ms,
            display_ms,
            total_ms,
        )
        with self._lock:
            self._records.append(entry)
        self._frame_index += 1

    # ------------------------------------------------------------------
    def _print_loop(self) -> None:
        while not self._stop_event.wait(timeout=1.0):
            self._print_stats()

    def _print_stats(self) -> None:
        with self._lock:
            snapshot = self._records[-self._window_size:]
        if not snapshot:
            return

        n = len(snapshot)
        labels = ["capture", "inference", "postproc", "policy", "display", "total"]

        def stats(vals: list) -> str:
            arr = np.array(vals)
            return f"min={arr.min():.1f} mean={arr.mean():.1f} p99={np.percentile(arr, 99):.1f} max={arr.max():.1f} ms"

        parts = " | ".join(
            f"{labels[i]}: {stats([r[i + 1] for r in snapshot])}"
            for i in range(len(labels))
        )
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[Latency {ts}] N={n} | {parts}")

    # ------------------------------------------------------------------
    def stop(self) -> None:
        self._stop_event.set()
        self._print_thread.join(timeout=2.0)

    def save_log(self, filename: str = "latency_log.txt") -> None:
        with self._lock:
            records_copy = list(self._records)
        log_dir = os.path.join("experimental_results", self._session_timestamp)
        os.makedirs(log_dir, exist_ok=True)
        filepath = os.path.join(log_dir, filename)
        with open(filepath, "w") as f:
            f.write(_HEADER + "\n")
            for r in records_copy:
                f.write(",".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in r) + "\n")
        print(f"[LatencyTracker] Saved {len(records_copy)} frames to {filepath}")

    @property
    def session_timestamp(self) -> str:
        return self._session_timestamp
