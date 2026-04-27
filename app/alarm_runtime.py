"""Runtime coordinator for orchestrator events and async effect execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, SimpleQueue
from typing import Union

from app.orchestrator import (
    AlarmOrchestrator,
    Effect,
    EnableAlarmButtonsEffect,
    LogTransitionEffect,
    PausePrinterEffect,
    ResumePrinterEffect,
    SaveFrameEffect,
    ShowAlarmEffect,
    ShutdownApplicationEffect,
    StopPrinterEffect,
    TurnLightOffEffect,
    TurnLightOnEffect,
)
from domain.models import AlarmEvent, DetectionResult, FramePacket
from ports.alarm_light import AlarmLightPort
from ports.logger import EventLoggerPort
from ports.printer import PrinterPort
from ports.ui import UiPort


@dataclass
class UserContinueRequested:
    pass


@dataclass
class UserStopRequested:
    pass


@dataclass
class PauseCompleted:
    frame_index: int


@dataclass
class PauseFailed:
    frame_index: int
    error: str


@dataclass
class ResumeCompleted:
    pass


@dataclass
class ResumeFailed:
    error: str


@dataclass
class StopCompleted:
    pass


@dataclass
class StopFailed:
    error: str


RuntimeEvent = Union[
    UserContinueRequested,
    UserStopRequested,
    PauseCompleted,
    PauseFailed,
    ResumeCompleted,
    ResumeFailed,
    StopCompleted,
    StopFailed,
]


class AlarmRuntime:
    """Coordinates event ingestion and executes effects outside orchestrator."""

    def __init__(
        self,
        orchestrator: AlarmOrchestrator,
        printer: PrinterPort,
        alarm_light: AlarmLightPort,
        ui: UiPort,
        logger: EventLoggerPort,
    ) -> None:
        self._orchestrator = orchestrator
        self._printer = printer
        self._light = alarm_light
        self._ui = ui
        self._logger = logger
        self._events: SimpleQueue[RuntimeEvent] = SimpleQueue()
        self._executor = ThreadPoolExecutor(max_workers=1)

    def handle_detection(self, result: DetectionResult, packet: FramePacket) -> None:
        effects = self._orchestrator.handle_detection(result, packet)
        self._dispatch_effects(effects)

    def process_pending_events(self, max_events: int = 100) -> None:
        processed = 0
        while processed < max_events:
            try:
                event = self._events.get_nowait()
            except Empty:
                break
            processed += 1
            effects = self._handle_event(event)
            self._dispatch_effects(effects)

    def request_continue(self) -> None:
        self._events.put(UserContinueRequested())

    def request_stop(self) -> None:
        self._events.put(UserStopRequested())

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _handle_event(self, event: RuntimeEvent) -> list[Effect]:
        if isinstance(event, UserContinueRequested):
            return self._orchestrator.on_user_continue()
        if isinstance(event, UserStopRequested):
            return self._orchestrator.on_user_stop()
        if isinstance(event, PauseCompleted):
            return self._orchestrator.on_pause_completed(event.frame_index)
        if isinstance(event, PauseFailed):
            return self._orchestrator.on_pause_failed(event.frame_index, event.error)
        if isinstance(event, ResumeCompleted):
            return self._orchestrator.on_resume_completed()
        if isinstance(event, ResumeFailed):
            return self._orchestrator.on_resume_failed(event.error)
        if isinstance(event, StopCompleted):
            return self._orchestrator.on_stop_completed()
        if isinstance(event, StopFailed):
            return self._orchestrator.on_stop_failed(event.error)
        return []

    def _dispatch_effects(self, effects: list[Effect]) -> None:
        for effect in effects:
            if isinstance(effect, ShowAlarmEffect):
                self._ui.show_alarm(on_continue=self.request_continue, on_stop=self.request_stop)
            elif isinstance(effect, EnableAlarmButtonsEffect):
                self._ui.enable_alarm_buttons()
            elif isinstance(effect, TurnLightOnEffect):
                self._light.turn_on()
            elif isinstance(effect, TurnLightOffEffect):
                self._light.turn_off()
            elif isinstance(effect, SaveFrameEffect):
                self._logger.save_frame(effect.frame, effect.label)
            elif isinstance(effect, LogTransitionEffect):
                self._logger.log_alarm(
                    AlarmEvent(
                        timestamp=datetime.now().isoformat(),
                        frame_index=effect.frame_index,
                        state_from=effect.from_s,
                        state_to=effect.to_s,
                        action=effect.action,
                    )
                )
            elif isinstance(effect, PausePrinterEffect):
                self._executor.submit(self._pause_task, effect.frame_index)
            elif isinstance(effect, ResumePrinterEffect):
                self._executor.submit(self._resume_task)
            elif isinstance(effect, StopPrinterEffect):
                self._executor.submit(self._stop_task)
            elif isinstance(effect, ShutdownApplicationEffect):
                self._ui.request_application_shutdown()

    def _pause_task(self, frame_index: int) -> None:
        try:
            self._printer.pause()
            self._events.put(PauseCompleted(frame_index))
        except Exception as exc:
            self._events.put(PauseFailed(frame_index, str(exc)))

    def _resume_task(self) -> None:
        try:
            self._printer.resume()
            self._events.put(ResumeCompleted())
        except Exception as exc:
            self._events.put(ResumeFailed(str(exc)))

    def _stop_task(self) -> None:
        try:
            self._printer.stop()
            self._events.put(StopCompleted())
        except Exception as exc:
            self._events.put(StopFailed(str(exc)))
