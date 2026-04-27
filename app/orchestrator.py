"""Application orchestration for alarm handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List

import numpy as np

from domain.models import DetectionResult, FramePacket
from domain.state_machine import AlarmStateMachine, State

if TYPE_CHECKING:
    from domain.policy import AlarmPolicy
    from ports.clock import ClockPort


class Effect:
    """Marker base class for actions produced by the orchestrator."""


@dataclass
class ShowAlarmEffect(Effect):
    pass


@dataclass
class PausePrinterEffect(Effect):
    frame_index: int


@dataclass
class ResumePrinterEffect(Effect):
    frame_index: int


@dataclass
class StopPrinterEffect(Effect):
    frame_index: int


@dataclass
class EnableAlarmButtonsEffect(Effect):
    pass


@dataclass
class TurnLightOnEffect(Effect):
    pass


@dataclass
class TurnLightOffEffect(Effect):
    pass


@dataclass
class SaveFrameEffect(Effect):
    frame: np.ndarray
    label: str


@dataclass
class LogTransitionEffect(Effect):
    frame_index: int
    from_s: str
    to_s: str
    action: str


@dataclass
class ShutdownApplicationEffect(Effect):
    pass


class AlarmOrchestrator:
    """Coordinates alarm logic and emits effects to be executed elsewhere."""

    def __init__(
        self,
        policy: AlarmPolicy,
        state_machine: AlarmStateMachine,
        clock: ClockPort,
    ) -> None:
        self._policy = policy
        self._sm = state_machine
        self._clock = clock
        self._alarm_frame_index: int = -1

    # ------------------------------------------------------------------
    # Called every frame by the pipeline
    # ------------------------------------------------------------------
    def handle_detection(self, result: DetectionResult, packet: FramePacket) -> List[Effect]:
        if self._sm.current_state == State.STOPPED:
            return []  # print was cancelled — alarm system disabled

        now = self._clock.perf_counter()
        should_alarm = self._policy.update(result.defect_count, now)

        if not should_alarm:
            return []
        if self._sm.current_state != State.MONITORING:
            return []  # already handling an alarm

        self._sm.trigger_alarm()
        self._alarm_frame_index = packet.index
        print(f"[ALARM] Defect alarm triggered at frame {packet.index}")
        self._sm.begin_pause()
        return [
            LogTransitionEffect(packet.index, "MONITORING", "ALARMED", "policy_triggered"),
            LogTransitionEffect(packet.index, "ALARMED", "PAUSING_PRINTER", "begin_pause"),
            TurnLightOnEffect(),
            SaveFrameEffect(packet.frame, f"defect_alarm_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
            ShowAlarmEffect(),
            PausePrinterEffect(packet.index),
        ]

    # ------------------------------------------------------------------
    # User actions (called from UI adapter)
    # ------------------------------------------------------------------
    def on_user_continue(self) -> List[Effect]:
        self._sm.on_user_continue()
        return [
            LogTransitionEffect(self._alarm_frame_index, "AWAITING_USER", "RESUMING", "user_continue"),
            ResumePrinterEffect(self._alarm_frame_index),
        ]

    def on_user_stop(self) -> List[Effect]:
        self._sm.on_user_stop()
        return [
            LogTransitionEffect(self._alarm_frame_index, "AWAITING_USER", "CANCELING", "user_stop"),
            StopPrinterEffect(self._alarm_frame_index),
        ]

    # ------------------------------------------------------------------
    # Background work
    # ------------------------------------------------------------------
    def on_pause_completed(self, frame_index: int) -> List[Effect]:
        self._sm.on_pause_complete()
        return [
            LogTransitionEffect(frame_index, "PAUSING_PRINTER", "AWAITING_USER", "pause_ok"),
            EnableAlarmButtonsEffect(),
        ]

    def on_pause_failed(self, frame_index: int, error: str) -> List[Effect]:
        self._sm.on_fault(error)
        return [LogTransitionEffect(frame_index, "PAUSING_PRINTER", "FAULT", error)]

    def on_resume_completed(self) -> List[Effect]:
        self._policy.reset()
        self._sm.on_action_done()
        return [
            TurnLightOffEffect(),
            LogTransitionEffect(self._alarm_frame_index, "RESUMING", "MONITORING", "resume_done"),
        ]

    def on_resume_failed(self, error: str) -> List[Effect]:
        self._sm.on_fault(error)
        return [LogTransitionEffect(self._alarm_frame_index, "RESUMING", "FAULT", error)]

    def on_stop_completed(self) -> List[Effect]:
        self._sm.on_cancel_done()
        return [
            TurnLightOffEffect(),
            LogTransitionEffect(self._alarm_frame_index, "CANCELING", "STOPPED", "cancel_done"),
            ShutdownApplicationEffect(),
        ]

    def on_stop_failed(self, error: str) -> List[Effect]:
        self._sm.on_fault(error)
        return [LogTransitionEffect(self._alarm_frame_index, "CANCELING", "FAULT", error)]
