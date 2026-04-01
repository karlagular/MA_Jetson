"""Port: event & data logging."""

from abc import ABC, abstractmethod
from typing import List

import numpy as np

from domain.models import AlarmEvent


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
