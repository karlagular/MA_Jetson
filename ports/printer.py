"""Port: printer control.

Re-exports the existing PrinterPort ABC so the rest of the new
codebase imports from ``ports.printer`` uniformly.
"""

from abc import ABC, abstractmethod


class PrinterPort(ABC):
    @abstractmethod
    def check_status(self) -> bool:
        """Check whether the printer is reachable."""

    @abstractmethod
    def pause(self) -> None:
        """Pause the current print job."""

    @abstractmethod
    def stop(self) -> None:
        """Stop / cancel the current print job."""

    @abstractmethod
    def resume(self) -> None:
        """Resume a paused print job."""
