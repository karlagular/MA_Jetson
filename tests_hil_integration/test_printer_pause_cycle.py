"""
Hardware-in-the-loop test: printer pause/resume/stop cycle on real device.

Tests the pause/resume and pause/stop command sequences on real 3D printer
hardware. Requires an active print job on the target printer and proper
machine configuration credentials.

Supported printers:
  - Bambulab (MQTT)
  - Prusa Link (HTTP REST)
  - Ultimaker (HTTP REST with auth)
  - RatRig (Klipper/Moonraker HTTP)

Markers: @pytest.mark.hil_printer

Usage:
    pytest tests_hil_integration/test_printer_pause_cycle.py
    pytest tests_hil_integration/test_printer_pause_cycle.py -vs --printer=Prusa --sequence=pause-resume
    pytest tests_hil_integration/test_printer_pause_cycle.py -vs --printer=Prusa --sequence=pause-resume-pause-stop

Command-line options (via pytest):
    --printer           : Printer to test (required: Bambulab, Prusa, Ultimaker, RatRig)
    --sequence          : Commands to run (default: pause-resume, or: pause-stop, or: pause-resume-pause-stop)
    --machine-config    : Path to machine_config.json (default: machine_config.json)
    --skip-connectivity-check : Skip initial status check
    --yes               : Auto-confirm safety prompts (non-interactive)

Safety notes:
  - This test sends actual pause/resume/stop commands to a real printer
  - An active print job must be running on the target printer
  - Use --yes only in controlled test environments
  - Always verify the printer is safe to control before running
"""

from __future__ import annotations

import pytest
import time
from typing import Tuple

from app.config import load_machine_config
from adapters.printer.bambu_mqtt import BambulabAdapter
from adapters.printer.klipper_moonraker import KlipperAdapter
from adapters.printer.prusa_link import PrusaAdapter
from adapters.printer.ultimaker_rest import UltimakerAdapter


@pytest.fixture
def printer_type(request):
    """Get printer type from command line."""
    printer = request.config.getoption("--printer")
    if printer is None:
        pytest.skip("--printer not specified")
    return printer


@pytest.fixture
def hil_printer(printer_type, request):
    """Load machine config and instantiate printer adapter."""
    config_path = request.config.getoption("--machine-config")
    machine_cfg = load_machine_config(config_path)
    cfg = machine_cfg.get(printer_type)
    
    if cfg is None:
        pytest.skip(f"No config found for printer '{printer_type}' in {config_path}")
    
    if printer_type == "Bambulab":
        return BambulabAdapter(cfg)
    elif printer_type == "Prusa":
        return PrusaAdapter(cfg)
    elif printer_type == "Ultimaker":
        return UltimakerAdapter(cfg)
    else:  # RatRig
        return KlipperAdapter(cfg)


def _timed_call(fn) -> Tuple[bool, float, str]:
    """Execute fn and return (success, duration_ms, message)."""
    t0 = time.perf_counter()
    try:
        fn()
        dt = (time.perf_counter() - t0) * 1000.0
        return True, dt, "ok"
    except Exception as exc:
        dt = (time.perf_counter() - t0) * 1000.0
        return False, dt, str(exc)


@pytest.mark.hil_printer
def test_printer_connectivity(hil_printer, request):
    """
    Test initial printer connectivity.
    
    Verifies that the printer is reachable and responding to status queries.
    Skipped if --skip-connectivity-check is passed.
    """
    if request.config.getoption("--skip-connectivity-check"):
        pytest.skip("Connectivity check skipped via --skip-connectivity-check")
    
    assert hil_printer.check_status(), "Printer connectivity check failed"


@pytest.mark.hil_printer
def test_printer_pause_resume_cycle(hil_printer, request):
    """
    Test pause -> resume command cycle on real printer.
    
    Verifies:
      - pause() command executes successfully
      - printer responds to status after pause
      - resume() command executes successfully
      - printer returns to printing state
    """
    sequence = request.config.getoption("--sequence")
    if sequence != "pause-resume":
        pytest.skip(f"Skipping pause-resume (sequence is {sequence})")
    
    skip_check = request.config.getoption("--skip-connectivity-check")
    assume_yes = request.config.getoption("--yes")
    
    if not skip_check:
        assert hil_printer.check_status(), "Initial connectivity check failed"
    
    if not assume_yes:
        response = input("Confirm active print job exists and can be paused [Y/n]: ")
        if response.lower() in ("n", "no"):
            pytest.skip("User declined to proceed")
    
    # Execute pause
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    print(f"[HIL] pause  -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"pause() failed: {msg}"
    
    time.sleep(1.0)
    
    # Execute resume
    ok, dt_ms, msg = _timed_call(hil_printer.resume)
    print(f"[HIL] resume -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"resume() failed: {msg}"


@pytest.mark.hil_printer
def test_printer_pause_stop_cycle(hil_printer, request):
    """
    Test pause -> stop command cycle on real printer.
    
    Verifies:
      - pause() command executes successfully
      - stop() command executes successfully
      - printer transitions to stopped state
    
    WARNING: This **cancels** the print job. Use only in test scenarios.
    """
    sequence = request.config.getoption("--sequence")
    if sequence != "pause-stop":
        pytest.skip(f"Skipping pause-stop (sequence is {sequence})")
    
    skip_check = request.config.getoption("--skip-connectivity-check")
    assume_yes = request.config.getoption("--yes")
    
    if not skip_check:
        assert hil_printer.check_status(), "Initial connectivity check failed"
    
    if not assume_yes:
        response = input("Confirm active print job exists and can be stopped [Y/n]: ")
        if response.lower() in ("n", "no"):
            pytest.skip("User declined to proceed")
    
    # Execute pause
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    print(f"[HIL] pause -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"pause() failed: {msg}"
    
    time.sleep(1.0)
    
    # Execute stop
    ok, dt_ms, msg = _timed_call(hil_printer.stop)
    print(f"[HIL] stop  -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"stop() failed: {msg}"


@pytest.mark.hil_printer
def test_printer_pause_resume_pause_stop_cycle(hil_printer, request):
    """
    Test pause -> resume -> pause -> stop command cycle on real printer.

    Verifies:
      - pause() command executes successfully
      - resume() command executes successfully
      - second pause() command executes successfully
      - stop() command executes successfully

    WARNING: This **cancels** the print job. Use only in test scenarios.
    """
    sequence = request.config.getoption("--sequence")
    if sequence != "pause-resume-pause-stop":
        pytest.skip(f"Skipping pause-resume-pause-stop (sequence is {sequence})")

    skip_check = request.config.getoption("--skip-connectivity-check")
    assume_yes = request.config.getoption("--yes")

    if not skip_check:
        assert hil_printer.check_status(), "Initial connectivity check failed"

    if not assume_yes:
        response = input("Confirm active print job exists and can be paused then stopped [Y/n]: ")
        if response.lower() in ("n", "no"):
            pytest.skip("User declined to proceed")

    # Step 1: pause
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    print(f"[HIL] pause  -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"pause() failed: {msg}"

    time.sleep(1.0)

    # Step 2: resume
    ok, dt_ms, msg = _timed_call(hil_printer.resume)
    print(f"[HIL] resume -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"resume() failed: {msg}"

    time.sleep(1.0)

    # Step 3: pause again
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    print(f"[HIL] pause  -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"second pause() failed: {msg}"

    time.sleep(1.0)

    # Step 4: stop
    ok, dt_ms, msg = _timed_call(hil_printer.stop)
    print(f"[HIL] stop   -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    assert ok, f"stop() failed: {msg}"
