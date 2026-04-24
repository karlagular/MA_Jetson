"""Unit tests for AlarmOrchestrator (event/effect level)."""

from unittest.mock import MagicMock

import numpy as np

from app.orchestrator import (
    AlarmOrchestrator,
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
from domain.state_machine import AlarmStateMachine, State


class FakeClock:
    def __init__(self, t: float = 1.0):
        self._t = t

    def perf_counter(self) -> float:
        return self._t


class TestAlarmOrchestrator:
    def _packet(self, idx: int = 7) -> FramePacket:
        return FramePacket(frame=np.zeros((6, 6, 3), dtype=np.uint8), index=idx, timestamp_ns=123)

    def test_handle_detection_no_effects_when_policy_suppresses(self):
        policy = MagicMock()
        policy.update.return_value = False
        sm = AlarmStateMachine()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())

        effects = orchestrator.handle_detection(DetectionResult(person_count=1), self._packet())
        assert effects == []

    def test_handle_detection_no_effects_when_not_monitoring(self):
        policy = MagicMock()
        policy.update.return_value = True
        sm = AlarmStateMachine()
        sm.trigger_alarm()  # ALARMED
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())

        effects = orchestrator.handle_detection(DetectionResult(person_count=1), self._packet())
        assert effects == []

    def test_handle_detection_triggers_expected_effects(self):
        policy = MagicMock()
        policy.update.return_value = True
        sm = AlarmStateMachine()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())

        effects = orchestrator.handle_detection(DetectionResult(person_count=2), self._packet(42))

        assert [type(e) for e in effects] == [
            LogTransitionEffect,
            LogTransitionEffect,
            TurnLightOnEffect,
            SaveFrameEffect,
            ShowAlarmEffect,
            PausePrinterEffect,
        ]
        assert effects[0].frame_index == 42
        assert effects[1].to_s == "PAUSING_PRINTER"
        assert effects[5].frame_index == 42
        assert sm.current_state == State.PAUSING_PRINTER

    def test_on_pause_completed_enables_alarm_buttons(self):
        policy = MagicMock()
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())

        effects = orchestrator.on_pause_completed(10)
        assert [type(e) for e in effects] == [LogTransitionEffect, EnableAlarmButtonsEffect]
        assert effects[0].frame_index == 10
        assert sm.current_state == State.AWAITING_USER

    def test_on_pause_failed_transitions_to_fault(self):
        policy = MagicMock()
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())

        effects = orchestrator.on_pause_failed(10, "timeout")
        assert len(effects) == 1
        assert isinstance(effects[0], LogTransitionEffect)
        assert effects[0].to_s == "FAULT"
        assert sm.current_state == State.FAULT

    def test_on_user_continue_emits_resume_effect(self):
        policy = MagicMock()
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_pause_complete()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())
        orchestrator._alarm_frame_index = 99

        effects = orchestrator.on_user_continue()
        assert [type(e) for e in effects] == [LogTransitionEffect, ResumePrinterEffect]
        assert effects[1].frame_index == 99
        assert sm.current_state == State.RESUMING

    def test_on_resume_completed_turns_light_off_and_resets_policy(self):
        policy = MagicMock()
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_pause_complete()
        sm.on_user_continue()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())
        orchestrator._alarm_frame_index = 77

        effects = orchestrator.on_resume_completed()
        assert [type(e) for e in effects] == [TurnLightOffEffect, LogTransitionEffect]
        policy.reset.assert_called_once()
        assert sm.current_state == State.MONITORING

    def test_on_stop_completed_transitions_to_stopped(self):
        policy = MagicMock()
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_pause_complete()
        sm.on_user_stop()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())
        orchestrator._alarm_frame_index = 5

        effects = orchestrator.on_stop_completed()
        assert [type(e) for e in effects] == [TurnLightOffEffect, LogTransitionEffect]
        assert sm.current_state == State.STOPPED

    def test_on_user_stop_emits_stop_effect(self):
        policy = MagicMock()
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_pause_complete()
        orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=FakeClock())
        orchestrator._alarm_frame_index = 33

        effects = orchestrator.on_user_stop()
        assert [type(e) for e in effects] == [LogTransitionEffect, StopPrinterEffect]
        assert effects[1].frame_index == 33
        assert sm.current_state == State.CANCELING
