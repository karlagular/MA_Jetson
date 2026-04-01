"""printer_control — hexagonal package exposing the same public API as the old module.

Public functions (backward-compatible):
    check_printer_status(machine) -> bool
    pause_print(machine) -> None   (non-blocking, daemon thread)
    stop_print(machine) -> None    (non-blocking, daemon thread)
    resume_print(machine) -> None  (non-blocking, daemon thread)
"""

import threading

from printer_control.factory import create_printer_adapter


def check_printer_status(machine: str) -> bool:
    """Check once whether the selected printer is reachable. Returns True if available."""
    try:
        adapter = create_printer_adapter(machine)
        return adapter.check_status()
    except Exception as e:
        print(f"[PrinterControl] Status check failed for '{machine}': {e}")
        return False


def pause_print(machine: str) -> None:
    """Non-blocking: sends the pause command in a daemon thread."""
    threading.Thread(target=_run_pause, args=(machine,), daemon=True).start()


def stop_print(machine: str) -> None:
    """Non-blocking: sends the stop command in a daemon thread."""
    threading.Thread(target=_run_stop, args=(machine,), daemon=True).start()


def resume_print(machine: str) -> None:
    """Non-blocking: sends the resume command in a daemon thread."""
    threading.Thread(target=_run_resume, args=(machine,), daemon=True).start()


def _run_pause(machine: str) -> None:
    try:
        adapter = create_printer_adapter(machine)
        adapter.pause()
    except Exception as e:
        print(f"[PrinterControl] Failed to pause '{machine}': {e}")


def _run_stop(machine: str) -> None:
    try:
        adapter = create_printer_adapter(machine)
        adapter.stop()
    except Exception as e:
        print(f"[PrinterControl] Failed to stop '{machine}': {e}")


def _run_resume(machine: str) -> None:
    try:
        adapter = create_printer_adapter(machine)
        adapter.resume()
    except Exception as e:
        print(f"[PrinterControl] Failed to resume '{machine}': {e}")
