"""Alarm policies — decide when a defect detection becomes an alarm."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque


class AlarmPolicy(ABC):
    """Port-like abstraction so policies can be swapped."""

    @abstractmethod
    def update(self, defect_count: int, now: float) -> bool:
        """Feed one frame observation. Return *True* when alarm should trigger."""

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state (e.g. after alarm handled)."""


class MofNPolicy(AlarmPolicy):
    """Trigger when a defect is detected in at least *m* of the last *n* frames.

    After an alarm is dismissed the policy remembers how many defects were
    in frame (the *baseline*).  The same count does NOT re-trigger.  Only a
    **new** defect (count goes above baseline) or a **re-appearance** after
    a disappearance can trigger a new alarm.

    A *disappearance* is any drop below the baseline that persists for
    ``disappear_frames`` consecutive frames.  Even a partial drop counts
    (e.g. 2 -> 1 for 3 frames lowers the baseline to 1, so a new second
    defect can trigger again).
    """

    def __init__(
        self,
        m: int = 100,
        n: int = 150,
        disappear_frames: int = 30,
    ) -> None:
        self._m = m
        self._n = n
        self._disappear_frames = disappear_frames

        self._window: deque[bool] = deque(maxlen=n)

        # Suppression state: after alarm dismissal, how many defects were
        # acknowledged.  Adjusted down when count stays below it.
        self._baseline_count: int = 0
        self._below_run: int = 0  # consecutive frames with count < baseline

    # ------------------------------------------------------------------
    def update(self, defect_count: int, now: float) -> bool:
        detected = defect_count > 0
        self._window.append(detected)

        # Track disappearance: consecutive frames below baseline
        if defect_count < self._baseline_count:
            self._below_run += 1
            if self._below_run >= self._disappear_frames:
                # Adjust baseline down to current level
                self._baseline_count = defect_count
                self._below_run = 0
        else:
            self._below_run = 0

        # Suppress if count is at or below the acknowledged baseline
        if defect_count <= self._baseline_count:
            return False

        # M-of-N gate
        if sum(self._window) < self._m:
            return False

        self._baseline_count = defect_count
        return True

    def reset(self) -> None:
        self._window.clear()
        # Do NOT clear baseline/below_run — the suppression state must survive
        # across alarm dismissals so the same defect doesn't re-trigger.
