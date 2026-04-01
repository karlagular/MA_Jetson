"""Alarm state machine — governs the lifecycle of a person-detection alarm."""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Optional


class State(Enum):
    MONITORING = auto()
    ALARMED = auto()
    PAUSING_PRINTER = auto()
    AWAITING_USER = auto()
    RESUMING = auto()
    CANCELING = auto()
    FAULT = auto()


# Valid transitions: (from_state) -> {to_states}
_TRANSITIONS = {
    State.MONITORING:       {State.ALARMED, State.FAULT},
    State.ALARMED:          {State.PAUSING_PRINTER, State.FAULT},
    State.PAUSING_PRINTER:  {State.AWAITING_USER, State.FAULT},
    State.AWAITING_USER:    {State.RESUMING, State.CANCELING, State.FAULT},
    State.RESUMING:         {State.MONITORING, State.FAULT},
    State.CANCELING:        {State.MONITORING, State.FAULT},
    State.FAULT:            {State.MONITORING},
}


class InvalidTransition(Exception):
    pass


class AlarmStateMachine:
    """Deterministic state machine for alarm flow.

    All side-effects (printer calls, UI updates) happen via callbacks
    registered by the orchestrator — the SM itself is pure logic.
    """

    def __init__(self, on_transition: Optional[Callable[[State, State], None]] = None) -> None:
        self._state = State.MONITORING
        self._on_transition = on_transition
        self._fault_error: Optional[str] = None

    # -- queries --------------------------------------------------------
    @property
    def current_state(self) -> State:
        return self._state

    @property
    def fault_error(self) -> Optional[str]:
        return self._fault_error

    # -- transitions ----------------------------------------------------
    def _go(self, target: State) -> None:
        if target not in _TRANSITIONS.get(self._state, set()):
            raise InvalidTransition(f"{self._state.name} -> {target.name}")
        old = self._state
        self._state = target
        if target != State.FAULT:
            self._fault_error = None
        if self._on_transition:
            self._on_transition(old, target)

    def trigger_alarm(self) -> None:
        """MONITORING -> ALARMED"""
        self._go(State.ALARMED)

    def begin_pause(self) -> None:
        """ALARMED -> PAUSING_PRINTER"""
        self._go(State.PAUSING_PRINTER)

    def on_pause_complete(self) -> None:
        """PAUSING_PRINTER -> AWAITING_USER"""
        self._go(State.AWAITING_USER)

    def on_user_continue(self) -> None:
        """AWAITING_USER -> RESUMING"""
        self._go(State.RESUMING)

    def on_user_stop(self) -> None:
        """AWAITING_USER -> CANCELING"""
        self._go(State.CANCELING)

    def on_action_done(self) -> None:
        """RESUMING | CANCELING -> MONITORING"""
        self._go(State.MONITORING)

    def on_fault(self, error: str) -> None:
        """Any -> FAULT"""
        self._fault_error = error
        self._go(State.FAULT)

    def acknowledge_fault(self) -> None:
        """FAULT -> MONITORING"""
        self._go(State.MONITORING)
