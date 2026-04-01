"""Alarm policies — decide when a person detection becomes an alarm."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque


class AlarmPolicy(ABC):
    """Port-like abstraction so policies can be swapped."""

    @abstractmethod
    def update(self, person_detected: bool, now: float) -> bool:
        """Feed one frame observation. Return *True* when alarm should trigger."""

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state (e.g. after alarm handled)."""


class MofNPolicy(AlarmPolicy):
    """Trigger when a person is detected in at least *m* of the last *n* frames.

    After an alarm triggers, a *cooldown_s* period must elapse (wall-clock)
    before the policy can trigger again.  This prevents alarm-spam when the
    user clicks "Continue" and the person is still briefly visible.
    """

    def __init__(self, m: int = 3, n: int = 5, cooldown_s: float = 10.0) -> None:
        self._m = m
        self._n = n
        self._cooldown_s = cooldown_s
        self._window: deque[bool] = deque(maxlen=n)
        self._last_trigger_time: float | None = None

    # ------------------------------------------------------------------
    def update(self, person_detected: bool, now: float) -> bool:
        self._window.append(person_detected)

        if sum(self._window) < self._m:
            return False

        if self._last_trigger_time is not None:
            if (now - self._last_trigger_time) < self._cooldown_s:
                return False

        self._last_trigger_time = now
        return True

    def reset(self) -> None:
        self._window.clear()
        self._last_trigger_time = None
