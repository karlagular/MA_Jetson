"""
Unit tests for domain.state_machine.AlarmStateMachine.

Covers all valid state transitions of the alarm FSM:
  MONITORING -> ALARMED -> PAUSING_PRINTER -> AWAITING_USER
    -> RESUMING -> MONITORING   (continue path)
    -> CANCELING -> STOPPED     (stop path)
  Any state -> FAULT -> MONITORING  (fault / recovery)

Also validates that illegal transitions raise InvalidTransition, that the
optional on_transition callback fires correctly, and that STOPPED is a
terminal state with no outgoing transitions.

Usage:
    pytest tests/unit/test_state_machine.py
    pytest tests/unit/test_state_machine.py -v
"""

import pytest
from domain.state_machine import AlarmStateMachine, InvalidTransition, State


class TestAlarmStateMachine:
    def test_initial_state_is_monitoring(self):
        sm = AlarmStateMachine()
        assert sm.current_state == State.MONITORING

    def test_happy_path_continue(self):
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        assert sm.current_state == State.ALARMED
        sm.begin_pause()
        assert sm.current_state == State.PAUSING_PRINTER
        sm.on_pause_complete()
        assert sm.current_state == State.AWAITING_USER
        sm.on_user_continue()
        assert sm.current_state == State.RESUMING
        sm.on_action_done()
        assert sm.current_state == State.MONITORING

    def test_happy_path_stop(self):
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_pause_complete()
        sm.on_user_stop()
        assert sm.current_state == State.CANCELING
        sm.on_cancel_done()
        assert sm.current_state == State.STOPPED

    def test_fault_from_pausing(self):
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_fault("connection refused")
        assert sm.current_state == State.FAULT
        assert sm.fault_error == "connection refused"

    def test_fault_recovery(self):
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_fault("timeout")
        sm.acknowledge_fault()
        assert sm.current_state == State.MONITORING
        assert sm.fault_error is None

    def test_invalid_transition_raises(self):
        sm = AlarmStateMachine()
        with pytest.raises(InvalidTransition):
            sm.begin_pause()  # MONITORING -> PAUSING_PRINTER not allowed

    def test_cannot_trigger_alarm_while_alarmed(self):
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        with pytest.raises(InvalidTransition):
            sm.trigger_alarm()  # ALARMED -> ALARMED not allowed

    def test_on_transition_callback(self):
        transitions = []
        sm = AlarmStateMachine(on_transition=lambda old, new: transitions.append((old, new)))
        sm.trigger_alarm()
        sm.begin_pause()
        assert transitions == [
            (State.MONITORING, State.ALARMED),
            (State.ALARMED, State.PAUSING_PRINTER),
        ]

    def test_fault_from_monitoring(self):
        sm = AlarmStateMachine()
        sm.on_fault("camera lost")
        assert sm.current_state == State.FAULT

    def test_cannot_resume_from_monitoring(self):
        sm = AlarmStateMachine()
        with pytest.raises(InvalidTransition):
            sm.on_user_continue()

    def test_stopped_is_terminal(self):
        """STOPPED allows no outgoing transitions."""
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_pause_complete()
        sm.on_user_stop()
        sm.on_cancel_done()
        assert sm.current_state == State.STOPPED
        with pytest.raises(InvalidTransition):
            sm.trigger_alarm()
        with pytest.raises(InvalidTransition):
            sm.on_fault("error")

    def test_canceling_goes_to_stopped_not_monitoring(self):
        sm = AlarmStateMachine()
        sm.trigger_alarm()
        sm.begin_pause()
        sm.on_pause_complete()
        sm.on_user_stop()
        assert sm.current_state == State.CANCELING
        with pytest.raises(InvalidTransition):
            sm.on_action_done()  # CANCELING -> MONITORING no longer valid
