"""Port: alarm light (e.g. signal tower, LED strip)."""

from abc import ABC, abstractmethod


class AlarmLightPort(ABC):
    @abstractmethod
    def turn_on(self) -> None:
        """Activate the alarm light."""

    @abstractmethod
    def turn_off(self) -> None:
        """Deactivate the alarm light."""
