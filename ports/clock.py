"""Port: clock — abstraction over wall-clock and monotonic time.

Enables deterministic testing of latency tracking and policy cooldowns.
"""

from abc import ABC, abstractmethod
from datetime import datetime


class ClockPort(ABC):
    @abstractmethod
    def perf_counter(self) -> float:
        """High-resolution monotonic counter (seconds)."""

    @abstractmethod
    def now(self) -> datetime:
        """Current wall-clock datetime."""
