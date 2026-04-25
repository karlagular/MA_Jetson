#!/usr/bin/env python3
"""Manual HIL script: orchestrator/runtime flow with real printer adapter."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    """Lightweight test clock wrapper around system time."""

    def perf_counter(self) -> float:
        return time.perf_counter()

    def now(self) -> datetime:
        return datetime.now()


class MemoryLogger(EventLoggerPort):
    """Fake logger used in this script to keep evidence in memory + console only."""

    def __init__(self) -> None:
        self.events: list[AlarmEvent] = []

    def log_alarm(self, event: AlarmEvent) -> None:
        self.events.append(event)
        print(
            f"[HIL][EVENT] frame={event.frame_index} "
            f"{event.state_from}->{event.state_to} action={event.action}"
        )

    def save_frame(self, frame: np.ndarray, label: str) -> None:
        del frame
        print(f"[HIL][EVENT] save_frame label={label}")

    def save_latency_log(self, records: list[tuple]) -> None:
        del records


@dataclass
class ConsoleUi(UiPort):
    """Fake UI that simulates user callbacks without launching the real Qt UI."""

    auto_user_action: str
    alarm_shown: bool = False
    buttons_enabled: bool = False
    _on_continue: Callable[[], None] | None = None
    _on_stop: Callable[[], None] | None = None

    def display_frame(self, frame: np.ndarray) -> None:
        del frame

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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Manual HIL: runtime -> printer flow",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--printer",
        choices=["Bambulab", "Prusa", "Ultimaker", "RatRig"],
        required=True,
        help="Select which real printer adapter should execute pause/resume/stop commands.",
    )
    p.add_argument(
        "--machine-config",
        default="machine_config.json",
        help="Path to machine configuration JSON containing printer endpoint and credential data.",
    )
    p.add_argument(
        "--auto-user-action",
        choices=["continue", "stop", "manual"],
        default="manual",
        help="How user decision is provided after pause: auto continue, auto stop, or manual terminal input.",
    )
    p.add_argument(
        "--timeout-s",
        type=float,
        default=25.0,
        help="Maximum wait time in seconds for each async state transition before failing the run.",
    )
    p.add_argument(
        "--skip-connectivity-check",
        action="store_true",
        help="Skip initial printer status check. Use only if connectivity was verified immediately before.",
    )
    return p.parse_args()


def _make_printer(printer_name: str, machine_cfg: dict):
    cfg = machine_cfg.get(printer_name)
    if cfg is None:
        raise ValueError(f"No config found for printer '{printer_name}'")

    if printer_name == "Bambulab":
        return BambulabAdapter(cfg)
    if printer_name == "Prusa":
        return PrusaAdapter(cfg)
    if printer_name == "Ultimaker":
        return UltimakerAdapter(cfg)
    if printer_name == "RatRig":
        return KlipperAdapter(cfg)
    raise ValueError(f"Unsupported printer '{printer_name}'")


def _wait_until(predicate, alarm_runtime: AlarmRuntime, timeout_s: float) -> bool:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        alarm_runtime.process_pending_events()
        if predicate():
            return True
        time.sleep(0.05)
    alarm_runtime.process_pending_events()
    return predicate()


def main() -> int:
    args = _parse_args()
    machine_cfg = load_machine_config(args.machine_config)
    printer = _make_printer(args.printer, machine_cfg)

    if not args.skip_connectivity_check:
        print("[HIL] Checking printer connectivity...")
        if not printer.check_status():
            print("[HIL][ERROR] Printer is not reachable")
            return 1

    clock = SystemClock()
    sm = AlarmStateMachine()
    policy = MofNPolicy(m=1, n=1)
    orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=clock)

    # Test doubles created for this script:
    # - MemoryLogger: fake logger, keeps events in memory and prints trace output.
    # - ConsoleUi: fake UI, captures callbacks and simulates operator actions.
    # - Synthetic frame/detection below: fake camera/inference stimulus to trigger alarm path deterministically.
    logger = MemoryLogger()
    ui = ConsoleUi(auto_user_action=args.auto_user_action)

    alarm_runtime = AlarmRuntime(
        orchestrator=orchestrator,
        printer=printer,
        alarm_light=DummyLight(),
        ui=ui,
        logger=logger,
    )

    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    packet = FramePacket(frame=frame, index=0, timestamp_ns=int(clock.perf_counter() * 1e9))
    detection = DetectionResult(person_detected=True, person_count=1)

    print("[HIL] Triggering synthetic person detection...")
    alarm_runtime.handle_detection(detection, packet)

    reached_waiting = _wait_until(
        lambda: sm.current_state in {State.AWAITING_USER, State.FAULT},
        alarm_runtime,
        timeout_s=args.timeout_s,
    )
    if not reached_waiting:
        print(f"[HIL][ERROR] Timeout before AWAITING_USER. state={sm.current_state.name}")
        alarm_runtime.shutdown()
        return 1
    if sm.current_state == State.FAULT:
        print("[HIL][ERROR] Flow entered FAULT during pause")
        alarm_runtime.shutdown()
        return 1

    if args.auto_user_action == "manual":
        choice = input("[HIL] User action? [continue/stop]: ").strip().lower()
        if choice == "stop":
            ui.trigger_stop()
            expected = State.STOPPED
        else:
            ui.trigger_continue()
            expected = State.MONITORING
    elif args.auto_user_action == "stop":
        expected = State.STOPPED
    else:
        expected = State.MONITORING

    ok = _wait_until(
        lambda: sm.current_state in {expected, State.FAULT},
        alarm_runtime,
        timeout_s=args.timeout_s,
    )

    print("\n[HIL][SUMMARY] Runtime->Printer flow")
    print(f"  alarm_shown        : {ui.alarm_shown}")
    print(f"  buttons_enabled    : {ui.buttons_enabled}")
    print(f"  final_state        : {sm.current_state.name}")
    print(f"  expected_state     : {expected.name}")
    print(f"  logged_events      : {len(logger.events)}")

    alarm_runtime.shutdown()
    if not ok:
        print("[HIL][ERROR] Timeout waiting for final state")
        return 1
    if sm.current_state == State.FAULT:
        print("[HIL][ERROR] Flow ended in FAULT")
        return 1
    return 0 if sm.current_state == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
