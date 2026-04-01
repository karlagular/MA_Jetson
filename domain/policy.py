"""Alarm policies — decide when a person detection becomes an alarm."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque


class AlarmPolicy(ABC):
    """Port-like abstraction so policies can be swapped."""

    @abstractmethod
    def update(self, person_count: int, now: float) -> bool:
        """Feed one frame observation. Return *True* when alarm should trigger."""

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state (e.g. after alarm handled)."""


class MofNPolicy(AlarmPolicy):
    """Trigger when a person is detected in at least *m* of the last *n* frames.

    After an alarm is dismissed the policy remembers how many persons were
    in frame (the *baseline*).  The same count does NOT re-trigger.  Only a
    **new** person (count goes above baseline) or a **re-appearance** (count
    drops to 0 for ``disappear_frames`` consecutive frames, then rises) can
    trigger a new alarm.
    """

    def __init__(
        self,
        m: int = 3,
        n: int = 5,
        cooldown_s: float = 10.0,
        disappear_frames: int = 3,
    ) -> None:
        self._m = m
        self._n = n
        self._cooldown_s = cooldown_s
        self._disappear_frames = disappear_frames

        self._window: deque[bool] = deque(maxlen=n)
        self._last_trigger_time: float | None = None

        # Suppression state: after alarm dismissal, how many persons were
        # acknowledged.  Stays active until all persons disappear.
        self._baseline_count: int = 0
        self._zero_run: int = 0  # consecutive frames with 0 persons

    # ------------------------------------------------------------------
    def update(self, person_count: int, now: float) -> bool:
        detected = person_count > 0
        self._window.append(detected)

        # Track disappearance: consecutive zero-count frames
        if person_count == 0:
            self._zero_run += 1
            if self._zero_run >= self._disappear_frames:
                self._baseline_count = 0
        else:
            self._zero_run = 0

        # Suppress if count is at or below the acknowledged baseline
        if person_count <= self._baseline_count:
            return False

        # M-of-N gate
        if sum(self._window) < self._m:
            return False

        # Cooldown gate
        if self._last_trigger_time is not None:
            if (now - self._last_trigger_time) < self._cooldown_s:
                return False

        self._last_trigger_time = now
        self._baseline_count = person_count
        return True

    def reset(self) -> None:
        self._window.clear()
        self._last_trigger_time = None
        # Do NOT clear baseline/zero_run — the suppression state must survive
        # across alarm dismissals so the same person doesn't re-trigger.
