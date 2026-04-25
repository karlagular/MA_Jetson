"""Integration test: stub camera + stub inference -> pipeline tick -> alarm fires."""

import time
import numpy as np
from datetime import datetime

from adapters.inference.stub_detections import StubDetections
from adapters.printer.fake_printer import FakePrinter
from adapters.alarm_light.dummy_light import DummyLight
from app.alarm_runtime import AlarmRuntime
from app.orchestrator import AlarmOrchestrator
from domain.models import AlarmEvent
from domain.policy import MofNPolicy
from domain.state_machine import AlarmStateMachine, State
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
        self._on_continue = None
        self._on_stop = None

    def display_frame(self, frame):
        self.frames_shown += 1

    def show_alarm(self, on_continue, on_stop):
        self.alarm_shown = True
        self._on_continue = on_continue
        self._on_stop = on_stop

    def dismiss_alarm(self):
        pass

    def enable_alarm_buttons(self):
        self.buttons_enabled = True

    def trigger_continue(self):
        if self._on_continue is not None:
            self._on_continue()

    def trigger_stop(self):
        if self._on_stop is not None:
            self._on_stop()


class TrackingLight(DummyLight):
    def __init__(self):
        self.on_calls = 0
        self.off_calls = 0

    def turn_on(self) -> None:
        self.on_calls += 1
        super().turn_on()

    def turn_off(self) -> None:
        self.off_calls += 1
        super().turn_off()


class FailablePrinter(FakePrinter):
    def __init__(self, fail_on_pause: bool = False):
        super().__init__()
        self._fail_on_pause = fail_on_pause

    def pause(self) -> None:
        super().pause()
        if self._fail_on_pause:
            raise RuntimeError("pause failed")


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
    @staticmethod
    def _wait_until(predicate, alarm_runtime, max_steps: int = 200, sleep_s: float = 0.001) -> bool:
        """Drain runtime events until predicate becomes true or timeout is reached."""
        for _ in range(max_steps):
            alarm_runtime.process_pending_events()
            if predicate():
                return True
            time.sleep(sleep_s)
        alarm_runtime.process_pending_events()
        return predicate()

    def test_alarm_triggers_after_m_of_n(self):
        """Person detected in frames 0-4 (m=3, n=5) -> alarm should fire."""
        clock = FakeClock()
        camera = FakeCamera(n_frames=10)
        stub = StubDetections(person_at_frames={0, 1, 2, 3, 4})
        printer = FakePrinter()
        light = DummyLight()
        ui = FakeUi()
        logger = MemoryLogger()
        policy = MofNPolicy(m=3, n=5)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(
            policy=policy,
            state_machine=sm,
            clock=clock,
        )

        alarm_runtime = AlarmRuntime(
            orchestrator=orchestrator,
            printer=printer,
            alarm_light=light,
            ui=ui,
            logger=logger,
        )

        tracker = LatencyTracker(clock=clock, window_size=60, session_id="test")

        pipeline = PipelineRunner(
            camera=camera, inference=stub, ui=ui,
            alarm_runtime=alarm_runtime, latency_tracker=tracker, clock=clock,
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
        policy = MofNPolicy(m=3, n=5)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(
            policy=policy,
            state_machine=sm,
            clock=clock,
        )

        alarm_runtime = AlarmRuntime(
            orchestrator=orchestrator,
            printer=printer,
            alarm_light=light,
            ui=ui,
            logger=logger,
        )

        tracker = LatencyTracker(clock=clock, window_size=60, session_id="test2")

        pipeline = PipelineRunner(
            camera=camera, inference=stub, ui=ui,
            alarm_runtime=alarm_runtime, latency_tracker=tracker, clock=clock,
        )

        camera.open()
        for _ in range(10):
            pipeline.tick()

        tracker.stop()

        assert not ui.alarm_shown
        assert len(printer.calls) == 0

    def test_alarm_continue_path_resumes_and_returns_to_monitoring(self):
        """Alarm -> pause -> user continue -> resume -> MONITORING."""
        clock = FakeClock()
        camera = FakeCamera(n_frames=12)
        stub = StubDetections(person_at_frames={0, 1, 2, 3, 4})
        printer = FakePrinter()
        light = TrackingLight()
        ui = FakeUi()
        logger = MemoryLogger()
        policy = MofNPolicy(m=3, n=5)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=clock)
        alarm_runtime = AlarmRuntime(
            orchestrator=orchestrator,
            printer=printer,
            alarm_light=light,
            ui=ui,
            logger=logger,
        )
        tracker = LatencyTracker(clock=clock, window_size=60, session_id="continue_path")
        pipeline = PipelineRunner(
            camera=camera,
            inference=stub,
            ui=ui,
            alarm_runtime=alarm_runtime,
            latency_tracker=tracker,
            clock=clock,
        )

        camera.open()
        for _ in range(10):
            pipeline.tick()

        assert ui.alarm_shown
        assert "pause" in printer.calls
        assert sm.current_state == State.AWAITING_USER

        ui.trigger_continue()
        assert self._wait_until(
            lambda: "resume" in printer.calls and sm.current_state == State.MONITORING,
            alarm_runtime,
        )

        assert "resume" in printer.calls
        assert sm.current_state == State.MONITORING
        assert ui.buttons_enabled
        assert light.on_calls >= 1
        assert light.off_calls >= 1
        assert not any(getattr(e, "state_to", "") == "FAULT" for e in logger.events)
        tracker.stop()

    def test_pause_failure_transitions_to_fault(self):
        """Pause exception should move flow to FAULT state."""
        clock = FakeClock()
        camera = FakeCamera(n_frames=10)
        stub = StubDetections(person_at_frames={0, 1, 2, 3, 4})
        printer = FailablePrinter(fail_on_pause=True)
        light = TrackingLight()
        ui = FakeUi()
        logger = MemoryLogger()
        policy = MofNPolicy(m=3, n=5)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=clock)
        alarm_runtime = AlarmRuntime(
            orchestrator=orchestrator,
            printer=printer,
            alarm_light=light,
            ui=ui,
            logger=logger,
        )
        tracker = LatencyTracker(clock=clock, window_size=60, session_id="pause_fault")
        pipeline = PipelineRunner(
            camera=camera,
            inference=stub,
            ui=ui,
            alarm_runtime=alarm_runtime,
            latency_tracker=tracker,
            clock=clock,
        )

        camera.open()
        for _ in range(8):
            pipeline.tick()

        alarm_runtime.process_pending_events()
        alarm_runtime.process_pending_events()

        assert ui.alarm_shown
        assert "pause" in printer.calls
        assert sm.current_state == State.FAULT
        assert any(e.state_to == "FAULT" for e in logger.events)
        tracker.stop()

    def test_alarm_stop_path_cancels_and_reaches_stopped(self):
        """Alarm -> pause -> user stop -> STOPPED and no retrigger."""
        clock = FakeClock()
        camera = FakeCamera(n_frames=20)
        stub = StubDetections(person_at_frames={0, 1, 2, 3, 4, 10, 11, 12})
        printer = FakePrinter()
        light = TrackingLight()
        ui = FakeUi()
        logger = MemoryLogger()
        policy = MofNPolicy(m=3, n=5)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=clock)
        alarm_runtime = AlarmRuntime(
            orchestrator=orchestrator,
            printer=printer,
            alarm_light=light,
            ui=ui,
            logger=logger,
        )
        tracker = LatencyTracker(clock=clock, window_size=60, session_id="stop_path")
        pipeline = PipelineRunner(
            camera=camera,
            inference=stub,
            ui=ui,
            alarm_runtime=alarm_runtime,
            latency_tracker=tracker,
            clock=clock,
        )

        camera.open()
        for _ in range(10):
            pipeline.tick()

        assert sm.current_state == State.AWAITING_USER
        ui.trigger_stop()
        assert self._wait_until(
            lambda: "stop" in printer.calls and sm.current_state == State.STOPPED,
            alarm_runtime,
        )

        assert "pause" in printer.calls
        assert "stop" in printer.calls
        assert sm.current_state == State.STOPPED
        assert light.off_calls >= 1

        calls_before = len(printer.calls)
        for _ in range(5):
            pipeline.tick()
        assert len(printer.calls) == calls_before
        tracker.stop()

    def test_multiple_alarm_cycles_do_not_leave_stale_state(self):
        """Two separated alarm cycles should complete cleanly without stale state."""
        clock = FakeClock()
        camera = FakeCamera(n_frames=25)
        stub = StubDetections(
            person_at_frames={0, 1, 2, 3, 4, 10, 11, 12, 13, 14}
        )
        printer = FakePrinter()
        light = TrackingLight()
        ui = FakeUi()
        logger = MemoryLogger()
        policy = MofNPolicy(m=3, n=5, disappear_frames=5)
        sm = AlarmStateMachine()

        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=clock)
        alarm_runtime = AlarmRuntime(
            orchestrator=orchestrator,
            printer=printer,
            alarm_light=light,
            ui=ui,
            logger=logger,
        )
        tracker = LatencyTracker(clock=clock, window_size=60, session_id="multi_cycles")
        pipeline = PipelineRunner(
            camera=camera,
            inference=stub,
            ui=ui,
            alarm_runtime=alarm_runtime,
            latency_tracker=tracker,
            clock=clock,
        )

        camera.open()
        for _ in range(20):
            pipeline.tick()
            if sm.current_state == State.AWAITING_USER:
                ui.trigger_continue()
                assert self._wait_until(
                    lambda: sm.current_state == State.MONITORING,
                    alarm_runtime,
                )

        pause_count = printer.calls.count("pause")
        resume_count = printer.calls.count("resume")

        assert pause_count >= 2
        assert resume_count >= 2
        assert sm.current_state == State.MONITORING
        assert ui.buttons_enabled
        assert light.off_calls >= 2
        assert not any(e.state_to == "FAULT" for e in logger.events)
        tracker.stop()
