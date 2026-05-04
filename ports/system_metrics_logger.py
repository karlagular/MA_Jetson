"""Port: background logging of system utilization metrics."""

from abc import ABC, abstractmethod


class SystemMetricsLoggerPort(ABC):
    @abstractmethod
    def start(self) -> None:
        """Start background metric collection."""

    @abstractmethod
    def stop(self) -> None:
        """Stop background metric collection and release resources."""
