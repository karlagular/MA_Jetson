from abc import ABC, abstractmethod


class PrinterPort(ABC):
    """Port defining the contract for printer control operations.

    All methods are synchronous (blocking I/O).
    Threading is handled by the calling layer.
    """

    @abstractmethod
    def check_status(self) -> bool:
        """Check whether the printer is reachable. Returns True if available."""

    @abstractmethod
    def pause(self) -> None:
        """Pause the current print job."""

    @abstractmethod
    def stop(self) -> None:
        """Stop / cancel the current print job."""

    @abstractmethod
    def resume(self) -> None:
        """Resume a paused print job."""
