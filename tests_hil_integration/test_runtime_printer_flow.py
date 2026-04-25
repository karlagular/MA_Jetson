"""
Hardware-in-the-loop test: alarm orchestrator/runtime flow with real printer.

Tests the full alarm response flow using a real printer adapter:
  1. Synthetic detection stimulus triggers the alarm
  2. AlarmOrchestrator decides to pause the printer
  3. AlarmRuntime executes the pause command on real hardware
  4. User action (continue or stop) is simulated or manually provided
  5. Runtime and orchestrator complete the recovery sequence

Supported printers: Bambulab, Prusa, Ultimaker, RatRig (as in test_printer_pause_cycle)

Markers: @pytest.mark.hil_full_system

Usage:
    pytest tests/integration/hil/test_runtime_printer_flow.py
    pytest tests/integration/hil/test_runtime_printer_flow.py -v --printer=Bambulab --auto-user-action=continue

Command-line options (via pytest):
    --printer              : Printer to test (required)
    --machine-config       : Path to machine_config.json (default: machine_config.json)
    --auto-user-action     : continue, stop, or manual (default: manual)
    --timeout-s            : Timeout per state transition (default: 25.0)
    --skip-connectivity-check : Skip initial printer status check

Safety notes:
  - An active print job is recommended but not strictly required
  - Pause command will be sent to real printer
  - If --auto-user-action=stop, the print job will be cancelled
  - Use in controlled environments only
"""

from __future__ import annotations

import pytest
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np

from adapters.alarm_light.dummy_light import DummyLight
from adapters.printer.bambu_mqtt import BambulabAdapter
from adapters.printer.klipper_moonraker import KlipperAdapter
from adapters.printer.prusa_link import PrusaAdapter
from adapters.printer.ultimaker_rest import UltimakerAdapter
from app.alarm_runtime import AlarmRuntime
from app.config import load_machine_config
from app.orchestrator import AlarmOrchestrator
from domain.models import AlarmEvent, DetectionResult, FramePacket
from domain.policy import MofNPolicy
from domain.state_machine import AlarmStateMachine, State
from ports.clock import ClockPort
from ports.logger import EventLoggerPort
from ports.ui import UiPort


class SystemClock(ClockPort):
    """Real system clock for HIL tests."""
    
    def perf_counter(self) -> float:
        return time.perf_counter()
    
    def now(self) -> datetime:
        return datetime.now()


class HilMemoryLogger(EventLoggerPort):
    """Fake logger for HIL tests (keeps events in memory + prints)."""
    
    def __init__(self) -> None:
        self.events: list[AlarmEvent] = []
    
    def log_alarm(self, event: AlarmEvent) -> None:
        self.events.append(event)
        print(f"[HIL][EVENT] frame={event.frame_index} {event.state_from}->{event.state_to} action={event.action}")
    
    def save_frame(self, frame: np.ndarray, label: str) -> None:
        print(f"[HIL][EVENT] save_frame label={label}")
    
    def save_latency_log(self, records: list[tuple]) -> None:
        pass


@dataclass
class HilConsoleUi(UiPort):
    """Fake UI for HIL tests (simulates user actions without Qt)."""
    
    auto_user_action: str
    alarm_shown: bool = False
    buttons_enabled: bool = False
    _on_continue: Callable[[], None] | None = None
    _on_stop: Callable[[], None] | None = None
    
    def display_frame(self, frame: np.ndarray) -> None:
        pass
    
    def show_alarm(self, on_continue: Callable[[], None], on_stop: Callable[[], None]) -> None:
        self.alarm_shown = True
        self._on_continue = on_continue
        self._on_stop = on_stop
        print("[HIL][UI] Alarm shown")
    
    def dismiss_alarm(self) -> None:
        print("[HIL][UI] Alarm dismissed")
    
    def enable_alarm_buttons(self) -> None:
        self.buttons_enabled = True
        print("[HIL][UI] Alarm buttons enabled")
        
        if self.auto_user_action == "continue" and self._on_continue is not None:
            print("[HIL][UI] Auto action: continue")
            self._on_continue()
        elif self.auto_user_action == "stop" and self._on_stop is not None:
            print("[HIL][UI] Auto action: stop")
            self._on_stop()
    
    def trigger_continue(self) -> None:
        if self._on_continue is not None:
            self._on_continue()
    
    def trigger_stop(self) -> None:
        if self._on_stop is not None:
            self._on_stop()


def pytest_addoption(parser):
    """Add HIL runtime options to pytest."""
    parser.addoption("--printer",
                     choices=["Bambulab", "Prusa", "Ultimaker", "RatRig"],
                     help="Printer to test (required)")
    parser.addoption("--machine-config", default="machine_config.json",
                     help="Path to machine_config.json")
    parser.addoption("--auto-user-action", default="manual",
                     choices=["continue", "stop", "manual"],
                     help="User action: auto-continue, auto-stop, or manual prompt")
    parser.addoption("--timeout-s", type=float, default=25.0,
                     help="Timeout per state transition")
    parser.addoption("--skip-connectivity-check", action="store_true",
                     help="Skip initial connectivity check")


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


def _wait_until(predicate, alarm_runtime: AlarmRuntime, timeout_s: float) -> bool:
    """Poll predicate until true or timeout."""
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        alarm_runtime.process_pending_events()
        if predicate():
            return True
        time.sleep(0.05)
    alarm_runtime.process_pending_events()
    return predicate()


@pytest.mark.hil_full_system
def test_runtime_printer_flow(hil_printer, request):
    """
    Test complete alarm -> pause -> user_action -> recovery flow.
    
    Verifies:
      - Synthetic detection triggers alarm and printer pause
      - Orchestrator transitions to AWAITING_USER
      - User action (auto or manual) proceeds
      - Runtime recovers to MONITORING or STOPPED as appropriate
      - No FAULT state is reached
    """
    auto_action = request.config.getoption("--auto-user-action")
    timeout_s = request.config.getoption("--timeout-s")
    skip_check = request.config.getoption("--skip-connectivity-check")
    
    if not skip_check:
        assert hil_printer.check_status(), "Printer connectivity check failed"
    
    # Build FSM, policy, orchestrator
    clock = SystemClock()
    sm = AlarmStateMachine()
    policy = MofNPolicy(m=1, n=1)  # Trigger on first detection
    orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=clock)
    
    # Build fake ports
    logger = HilMemoryLogger()
    ui = HilConsoleUi(auto_user_action=auto_action)
    
    # Create runtime with real printer
    alarm_runtime = AlarmRuntime(
        orchestrator=orchestrator,
        printer=hil_printer,
        alarm_light=DummyLight(),
        ui=ui,
        logger=logger,
    )
    
    # Inject synthetic detection stimulus
    print("[HIL] Triggering synthetic detection...")
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    packet = FramePacket(frame=frame, index=0, timestamp_ns=int(clock.perf_counter() * 1e9))
    detection = DetectionResult(person_detected=True, person_count=1)
    
    alarm_runtime.handle_detection(detection, packet)
    
    # Wait for pause and button enable
    print("[HIL] Waiting for alarm state (AWAITING_USER or FAULT)...")
    reached_waiting = _wait_until(
        lambda: sm.current_state in {State.AWAITING_USER, State.FAULT},
        alarm_runtime,
        timeout_s=timeout_s,
    )
    assert reached_waiting, f"Timeout before AWAITING_USER. state={sm.current_state.name}"
    assert sm.current_state != State.FAULT, "Flow entered FAULT state during pause"
    assert ui.alarm_shown, "Alarm was not shown to user"
    
    # Perform user action
    if auto_action == "manual":
        choice = input("[HIL] User action? [continue/stop]: ").strip().lower()
        if choice == "stop":
            ui.trigger_stop()
            expected_state = State.STOPPED
        else:
            ui.trigger_continue()
            expected_state = State.MONITORING
    elif auto_action == "stop":
        expected_state = State.STOPPED
    else:  # continue
        expected_state = State.MONITORING
    
    # Wait for final state
    print(f"[HIL] Waiting for final state ({expected_state.name})...")
    reached_final = _wait_until(
        lambda: sm.current_state in {expected_state, State.FAULT},
        alarm_runtime,
        timeout_s=timeout_s,
    )
    
    assert reached_final, f"Timeout waiting for {expected_state.name}"
    assert sm.current_state != State.FAULT, "Flow ended in FAULT state"
    assert sm.current_state == expected_state, f"Expected {expected_state.name}, got {sm.current_state.name}"
    
    alarm_runtime.shutdown()
    
    print("\n[HIL][SUMMARY]")
    print(f"  alarm_shown      : {ui.alarm_shown}")
    print(f"  buttons_enabled  : {ui.buttons_enabled}")
    print(f"  final_state      : {sm.current_state.name}")
    print(f"  events_logged    : {len(logger.events)}")
