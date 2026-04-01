"""Integration test: stub camera + stub inference -> pipeline tick -> alarm fires."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from datetime import datetime

from adapters.inference.stub_detections import StubDetections
from adapters.printer.fake_printer import FakePrinter
from adapters.alarm_light.dummy_light import DummyLight
from domain.models import AlarmEvent
from domain.policy import MofNPolicy
from domain.state_machine import AlarmStateMachine, State
from domain.use_cases import AlarmOrchestrator
from pipeline.latency import LatencyTracker
from pipeline.processor import PipelineRunner
from pipeline.steps import draw_overlay
from ports.camera import CameraPort
from ports.clock import ClockPort
from ports.logger import EventLoggerPort
from ports.ui import UiPort


# --- Fakes / stubs for ports not under test ---

class FakeClock(ClockPort):
    def __init__(self):
        self._t = 0.0

    def perf_counter(self) -> float:
        self._t += 0.001
        return self._t

    def now(self) -> datetime:
        return datetime(2026, 1, 1)


class FakeCamera(CameraPort):
    def __init__(self, n_frames: int = 20):
        self._n = n_frames
        self._i = 0

    def open(self) -> bool:
        return True

    def read_frame(self):
        if self._i >= self._n:
            return False, None
        self._i += 1
        return True, np.zeros((100, 100, 3), dtype=np.uint8)

    def close(self):
        pass


class FakeUi(UiPort):
    def __init__(self):
        self.frames_shown = 0
        self.alarm_shown = False
        self.buttons_enabled = False

    def display_frame(self, frame):
        self.frames_shown += 1

    def show_alarm(self, on_continue, on_stop):
        self.alarm_shown = True

    def dismiss_alarm(self):
        pass

    def enable_alarm_buttons(self):
        self.buttons_enabled = True


class MemoryLogger(EventLoggerPort):
    def __init__(self):
        self.events = []
        self.frames_saved = []

    def log_alarm(self, event):
        self.events.append(event)

    def save_frame(self, frame, label):
        self.frames_saved.append(label)

    def save_latency_log(self, records):
        pass


class TestPipelineReplay:
    def test_alarm_triggers_after_m_of_n(self):
        """Person detected in frames 0-4 (m=3, n=5) -> alarm should fire."""
        clock = FakeClock()
        camera = FakeCamera(n_frames=10)
        stub = StubDetections(person_at_frames={0, 1, 2, 3, 4})
        printer = FakePrinter()
        light = DummyLight()
        ui = FakeUi()
        logger = MemoryLogger()
        policy = MofNPolicy(m=3, n=5, cooldown_s=0)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(
            policy=policy, state_machine=sm, printer=printer,
            alarm_light=light, ui=ui, logger=logger, clock=clock,
        )

        tracker = LatencyTracker(clock=clock, window_size=60, session_id="test")

        pipeline = PipelineRunner(
            camera=camera, inference=stub, ui=ui,
            orchestrator=orchestrator, latency_tracker=tracker, clock=clock,
        )

        camera.open()
        for _ in range(10):
            pipeline.tick()

        tracker.stop()

        # Alarm should have been shown at some point
        assert ui.alarm_shown, "Alarm dialog was never shown"
        # Printer should have been paused
        assert "pause" in printer.calls, f"Expected pause call, got: {printer.calls}"
        # Logger should have recorded events
        assert len(logger.events) > 0, "No alarm events logged"

    def test_no_alarm_without_detections(self):
        """No person detected -> no alarm."""
        clock = FakeClock()
        camera = FakeCamera(n_frames=10)
        stub = StubDetections(person_at_frames=set())
        printer = FakePrinter()
        light = DummyLight()
        ui = FakeUi()
        logger = MemoryLogger()
        policy = MofNPolicy(m=3, n=5, cooldown_s=0)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(
            policy=policy, state_machine=sm, printer=printer,
            alarm_light=light, ui=ui, logger=logger, clock=clock,
        )

        tracker = LatencyTracker(clock=clock, window_size=60, session_id="test2")

        pipeline = PipelineRunner(
            camera=camera, inference=stub, ui=ui,
            orchestrator=orchestrator, latency_tracker=tracker, clock=clock,
        )

        camera.open()
        for _ in range(10):
            pipeline.tick()

        tracker.stop()

        assert not ui.alarm_shown
        assert len(printer.calls) == 0
