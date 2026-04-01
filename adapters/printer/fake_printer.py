"""Fake printer adapter for testing — logs calls, always succeeds."""

from __future__ import annotations

from ports.printer import PrinterPort


class FakePrinter(PrinterPort):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def check_status(self) -> bool:
        self.calls.append("check_status")
        return True

    def pause(self) -> None:
        self.calls.append("pause")
        print("[FakePrinter] pause")

    def stop(self) -> None:
        self.calls.append("stop")
        print("[FakePrinter] stop")

    def resume(self) -> None:
        self.calls.append("resume")
        print("[FakePrinter] resume")
