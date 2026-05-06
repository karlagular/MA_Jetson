"""Port: event & data logging."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

import numpy as np

from domain.models import AlarmEvent, BBox


class EventLoggerPort(ABC):
    @abstractmethod
    def log_alarm(self, event: AlarmEvent) -> None:
        """Persist an alarm-related event."""

    @abstractmethod
    def save_frame(self, frame: np.ndarray, label: str) -> None:
        """Save a frame image (e.g. JPEG) with the given label."""

    @abstractmethod
    def save_latency_log(self, records: List[tuple]) -> None:
        """Write latency records to persistent storage."""

    def save_bboxes(self, boxes: List[BBox], label: str) -> None:
        """Optionally persist model bbox output in structured form."""
        return

    def save_run_summary(
        self,
        frame_count: int,
        alarms_activated: int | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        """Optionally persist run summary metadata (implementations may no-op)."""
        return
