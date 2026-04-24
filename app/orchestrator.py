"""Application orchestration for alarm handling."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING

from domain.models import AlarmEvent, DetectionResult, FramePacket
from domain.state_machine import AlarmStateMachine, State

if TYPE_CHECKING:
    from domain.policy import AlarmPolicy
    from ports.alarm_light import AlarmLightPort
    from ports.clock import ClockPort
    from ports.logger import EventLoggerPort
    from ports.printer import PrinterPort
    from ports.ui import UiPort


class AlarmOrchestrator:
    """Coordinates alarm logic across domain + ports.

    All printer / light calls run on daemon threads so the
    hot path (frame loop) is never blocked.
    """

    def __init__(
        self,
        policy: AlarmPolicy,
        state_machine: AlarmStateMachine,
        printer: PrinterPort,
        alarm_light: AlarmLightPort,
        ui: UiPort,
        logger: EventLoggerPort,
        clock: ClockPort,
    ) -> None:
        self._policy = policy
        self._sm = state_machine
        self._printer = printer
        self._light = alarm_light
        self._ui = ui
        self._logger = logger
        self._clock = clock
        self._alarm_frame_index: int = -1

    # ------------------------------------------------------------------
    # Called every frame by the pipeline
    # ------------------------------------------------------------------
    def handle_detection(self, result: DetectionResult, packet: FramePacket) -> None:
        if self._sm.current_state == State.STOPPED:
            return  # print was cancelled — alarm system disabled

        now = self._clock.perf_counter()
        should_alarm = self._policy.update(result.person_count, now)

        if not should_alarm:
            return
        if self._sm.current_state != State.MONITORING:
            return  # already handling an alarm

        self._sm.trigger_alarm()
        self._alarm_frame_index = packet.index
        print(f"[ALARM] Person alarm triggered at frame {packet.index}")
        self._log_transition(packet.index, "MONITORING", "ALARMED", "policy_triggered")
        self._sm.begin_pause()
        self._log_transition(packet.index, "ALARMED", "PAUSING_PRINTER", "begin_pause")
        self._light.turn_on()
        self._logger.save_frame(packet.frame, f"person_alarm_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        threading.Thread(target=self._pause_and_await, args=(packet.index,), daemon=True).start()

    # ------------------------------------------------------------------
    # User actions (called from UI adapter)
    # ------------------------------------------------------------------
    def on_user_continue(self) -> None:
        self._log_transition(self._alarm_frame_index, "AWAITING_USER", "RESUMING", "user_continue")
        self._sm.on_user_continue()
        threading.Thread(target=self._resume_and_finish, daemon=True).start()

    def on_user_stop(self) -> None:
        self._log_transition(self._alarm_frame_index, "AWAITING_USER", "CANCELING", "user_stop")
        self._sm.on_user_stop()
        threading.Thread(target=self._cancel_and_finish, daemon=True).start()

    # ------------------------------------------------------------------
    # Background work
    # ------------------------------------------------------------------
    def _pause_and_await(self, frame_index: int) -> None:
        # Always show alarm window immediately; action buttons stay disabled
        # until the printer pause has been confirmed.
        self._ui.show_alarm(on_continue=self.on_user_continue, on_stop=self.on_user_stop)

        try:
            self._printer.pause()
            self._sm.on_pause_complete()
            self._log_transition(frame_index, "PAUSING_PRINTER", "AWAITING_USER", "pause_ok")
            self._ui.enable_alarm_buttons()
        except Exception as exc:
            print(f"[ALARM] Printer pause failed: {exc}")
            self._sm.on_fault(str(exc))
            self._log_transition(frame_index, "PAUSING_PRINTER", "FAULT", str(exc))

    def _resume_and_finish(self) -> None:
        try:
            self._printer.resume()
            self._light.turn_off()
            self._policy.reset()
            self._sm.on_action_done()
            self._log_transition(self._alarm_frame_index, "RESUMING", "MONITORING", "resume_done")
        except Exception as exc:
            self._sm.on_fault(str(exc))
            self._log_transition(self._alarm_frame_index, "RESUMING", "FAULT", str(exc))

    def _cancel_and_finish(self) -> None:
        try:
            self._printer.stop()
            self._light.turn_off()
            self._sm.on_cancel_done()
            self._log_transition(self._alarm_frame_index, "CANCELING", "STOPPED", "cancel_done")
        except Exception as exc:
            self._sm.on_fault(str(exc))
            self._log_transition(self._alarm_frame_index, "CANCELING", "FAULT", str(exc))

    # ------------------------------------------------------------------
    def _log_transition(self, frame_index: int, from_s: str, to_s: str, action: str) -> None:
        event = AlarmEvent(
            timestamp=datetime.now().isoformat(),
            frame_index=frame_index,
            state_from=from_s,
            state_to=to_s,
            action=action,
        )
        self._logger.log_alarm(event)