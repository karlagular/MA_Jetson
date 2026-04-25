"""Port: user interface."""

from abc import ABC, abstractmethod
from typing import Callable, Optional

import numpy as np


class ConfigUiPort(ABC):
    """One-shot config dialog — shown before the main window exists."""

    @abstractmethod
    def request_session_config(self, available_models: list):
        """Ask the user for session config. Returns an ExperimentConfig or None if cancelled."""


class UiPort(ABC):
    @abstractmethod
    def display_frame(self, frame: np.ndarray) -> None:
        """Show a processed frame to the user."""

    @abstractmethod
    def show_alarm(self, on_continue: Callable[[], None], on_stop: Callable[[], None]) -> None:
        """Present an alarm dialog. Callbacks are invoked on user action."""

    @abstractmethod
    def dismiss_alarm(self) -> None:
        """Programmatically close the alarm dialog (if open)."""

    @abstractmethod
    def enable_alarm_buttons(self) -> None:
        """Enable the continue/stop buttons in the alarm dialog (called after printer pause settles)."""
