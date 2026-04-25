"""
Unit tests for app.alarm_runtime.AlarmRuntime.

Tests the runtime layer that bridges the AlarmOrchestrator (pure domain
logic) with the actual port implementations (printer, light, UI, logger)
using a thread-pool executor for blocking I/O.

Fake port implementations (FakePrinter, FakeLight, FakeUi, FakeLogger) are
defined locally so no real hardware or network is involved.

Coverage:
  - request_continue / request_stop enqueue the correct internal events.
  - process_pending_events respects the max_events limit.
  - _dispatch_effects routes each effect type to the correct port or
    submits it to the thread-pool executor.
  - handle_detection calls the orchestrator and dispatches returned effects.
  - _pause_task / _resume_task / _stop_task enqueue Completed or Failed
    events depending on whether the printer call raises.
  - _handle_event routes runtime events back to the orchestrator.

Usage:
    pytest tests/unit/test_alarm_runtime.py
    pytest tests/unit/test_alarm_runtime.py -v
"""

from unittest.mock import MagicMock

import numpy as np

from app.alarm_runtime import (
    AlarmRuntime,
    PauseCompleted,
    PauseFailed,
    ResumeCompleted,
    ResumeFailed,
    StopCompleted,
    StopFailed,
    UserContinueRequested,
    UserStopRequested,
)
from app.orchestrator import (
    EnableAlarmButtonsEffect,
    LogTransitionEffect,
    PausePrinterEffect,
    ResumePrinterEffect,
    SaveFrameEffect,
    ShowAlarmEffect,
    StopPrinterEffect,
    TurnLightOffEffect,
    TurnLightOnEffect,
)
from domain.models import DetectionResult, FramePacket


class FakePrinter:
    def __init__(self):
        self.pause_calls = 0
        self.resume_calls = 0
        self.stop_calls = 0
        self.pause_error = None
        self.resume_error = None
        self.stop_error = None

    def check_status(self):
        return True

    def pause(self):
        self.pause_calls += 1
        if self.pause_error:
            raise self.pause_error

    def resume(self):
        self.resume_calls += 1
        if self.resume_error:
            raise self.resume_error

    def stop(self):
        self.stop_calls += 1
        if self.stop_error:
            raise self.stop_error


class FakeLight:
    def __init__(self):
        self.on_calls = 0
        self.off_calls = 0

    def turn_on(self):
        self.on_calls += 1

    def turn_off(self):
        self.off_calls += 1


class FakeUi:
    def __init__(self):
        self.alarm_shown = 0
        self.buttons_enabled = 0
        self.callbacks = None

    def display_frame(self, frame):
        pass

    def show_alarm(self, on_continue, on_stop):
        self.alarm_shown += 1
        self.callbacks = (on_continue, on_stop)

    def dismiss_alarm(self):
        pass

    def enable_alarm_buttons(self):
        self.buttons_enabled += 1


class FakeLogger:
    def __init__(self):
        self.events = []
        self.frames = []

    def log_alarm(self, event):
        self.events.append(event)

    def save_frame(self, frame, label):
        self.frames.append((frame, label))

    def save_latency_log(self, records):
        pass


class TestAlarmRuntime:
    def _runtime(self):
        orchestrator = MagicMock()
        printer = FakePrinter()
        light = FakeLight()
        ui = FakeUi()
        logger = FakeLogger()
        runtime = AlarmRuntime(orchestrator, printer, light, ui, logger)
        return runtime, orchestrator, printer, light, ui, logger

    def test_request_continue_event_is_processed(self):
        runtime, orchestrator, *_ = self._runtime()
        orchestrator.on_user_continue.return_value = []

        runtime.request_continue()
        runtime.process_pending_events()

        orchestrator.on_user_continue.assert_called_once()

    def test_request_stop_event_is_processed(self):
        runtime, orchestrator, *_ = self._runtime()
        orchestrator.on_user_stop.return_value = []

        runtime.request_stop()
        runtime.process_pending_events()

        orchestrator.on_user_stop.assert_called_once()

    def test_process_pending_events_respects_max_events(self):
        runtime, orchestrator, *_ = self._runtime()
        orchestrator.on_user_continue.return_value = []

        for _ in range(5):
            runtime.request_continue()
        runtime.process_pending_events(max_events=2)

        assert orchestrator.on_user_continue.call_count == 2

    def test_dispatch_effects_to_ports_and_executor(self):
        runtime, orchestrator, _printer, light, ui, logger = self._runtime()
        runtime._executor = MagicMock()

        frame = np.zeros((3, 3, 3), dtype=np.uint8)
        effects = [
            ShowAlarmEffect(),
            EnableAlarmButtonsEffect(),
            TurnLightOnEffect(),
            TurnLightOffEffect(),
            SaveFrameEffect(frame=frame, label="lab"),
            LogTransitionEffect(frame_index=10, from_s="A", to_s="B", action="go"),
            PausePrinterEffect(frame_index=10),
            ResumePrinterEffect(frame_index=10),
            StopPrinterEffect(frame_index=10),
        ]

        runtime._dispatch_effects(effects)

        assert ui.alarm_shown == 1
        assert ui.buttons_enabled == 1
        assert light.on_calls == 1
        assert light.off_calls == 1
        assert len(logger.frames) == 1
        assert logger.frames[0][1] == "lab"
        assert len(logger.events) == 1
        assert logger.events[0].frame_index == 10
        assert logger.events[0].state_from == "A"
        assert runtime._executor.submit.call_count == 3

    def test_handle_detection_calls_orchestrator_and_dispatches(self):
        runtime, orchestrator, _printer, light, _ui, _logger = self._runtime()
        orchestrator.handle_detection.return_value = [TurnLightOnEffect()]
        packet = FramePacket(frame=np.zeros((2, 2, 3), dtype=np.uint8), index=1, timestamp_ns=1)

        runtime.handle_detection(DetectionResult(person_count=1), packet)

        orchestrator.handle_detection.assert_called_once()
        assert light.on_calls == 1

    def test_pause_task_success_enqueues_completed_event(self):
        runtime, _orchestrator, printer, *_ = self._runtime()
        runtime._pause_task(6)
        event = runtime._events.get_nowait()

        assert printer.pause_calls == 1
        assert isinstance(event, PauseCompleted)
        assert event.frame_index == 6

    def test_pause_task_failure_enqueues_failed_event(self):
        runtime, _orchestrator, printer, *_ = self._runtime()
        printer.pause_error = RuntimeError("pause failed")

        runtime._pause_task(7)
        event = runtime._events.get_nowait()

        assert isinstance(event, PauseFailed)
        assert event.frame_index == 7
        assert "pause failed" in event.error

    def test_resume_task_success_and_failure_events(self):
        runtime, _orchestrator, printer, *_ = self._runtime()

        runtime._resume_task()
        event_ok = runtime._events.get_nowait()
        assert isinstance(event_ok, ResumeCompleted)

        printer.resume_error = RuntimeError("resume failed")
        runtime._resume_task()
        event_fail = runtime._events.get_nowait()
        assert isinstance(event_fail, ResumeFailed)
        assert "resume failed" in event_fail.error

    def test_stop_task_success_and_failure_events(self):
        runtime, _orchestrator, printer, *_ = self._runtime()

        runtime._stop_task()
        event_ok = runtime._events.get_nowait()
        assert isinstance(event_ok, StopCompleted)

        printer.stop_error = RuntimeError("stop failed")
        runtime._stop_task()
        event_fail = runtime._events.get_nowait()
        assert isinstance(event_fail, StopFailed)
        assert "stop failed" in event_fail.error

    def test_handle_event_routes_runtime_events(self):
        runtime, orchestrator, *_ = self._runtime()
        orchestrator.on_pause_completed.return_value = []
        orchestrator.on_pause_failed.return_value = []

        runtime._handle_event(PauseCompleted(11))
        runtime._handle_event(PauseFailed(11, "x"))

        orchestrator.on_pause_completed.assert_called_once_with(11)
        orchestrator.on_pause_failed.assert_called_once_with(11, "x")
