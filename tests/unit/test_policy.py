"""
Unit tests for domain.policy.MofNPolicy.

Verifies the M-of-N sliding-window detection policy used to decide when an
alarm should fire:
  - Trigger only when at least M detections appear in the last N frames.
  - Baseline suppression prevents re-triggering for the same number of
    detected defects after an alarm is dismissed.
  - Disappear-frames grace period: baseline resets only after the defect
    count stays below the baseline for a configurable number of consecutive
    frames.

No real camera or printer is involved; all tests run in pure Python.

Usage:
    pytest tests/unit/test_policy.py
    pytest tests/unit/test_policy.py -v          # verbose
    pytest tests/unit/test_policy.py -k sliding  # run only sliding-window test
"""

from domain.policy import MofNPolicy


class TestMofNPolicy:
    def test_does_not_trigger_below_threshold(self):
        p = MofNPolicy(m=3, n=5)
        # Only 2 detections in 5 frames -> no trigger
        assert not p.update(1, 1.0)
        assert not p.update(1, 2.0)
        assert not p.update(0, 3.0)
        assert not p.update(0, 4.0)
        assert not p.update(0, 5.0)

    def test_triggers_at_threshold(self):
        p = MofNPolicy(m=3, n=5)
        p.update(1, 1.0)
        p.update(1, 2.0)
        result = p.update(1, 3.0)
        assert result is True

    def test_baseline_suppresses_retrigger(self):
        p = MofNPolicy(m=3, n=5)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # triggers

        # Baseline is now 1 — same count is suppressed
        p.reset()  # simulate alarm dismissal
        p.update(1, 4.0)
        assert p.update(1, 5.0) is False

    def test_triggers_again_after_disappearance(self):
        p = MofNPolicy(m=3, n=5, disappear_frames=3)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # triggers, baseline=1
        p.reset()

        # Defect still visible — suppressed
        assert p.update(1, 4.0) is False
        assert p.update(1, 5.0) is False

        # Defect disappears for 3 consecutive frames -> baseline clears
        assert p.update(0, 6.0) is False
        assert p.update(0, 7.0) is False
        assert p.update(0, 8.0) is False  # zero_run=3, baseline reset to 0

        # Re-detect: need M detections again to trigger
        p.update(1, 9.0)
        p.update(1, 10.0)
        assert p.update(1, 11.0) is True  # new alarm

    def test_same_defect_suppressed_after_dismissal(self):
        p = MofNPolicy(m=3, n=5, disappear_frames=3)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # triggers, baseline=1
        p.reset()

        # Same defect stays — never re-triggers
        for t in range(4, 20):
            assert p.update(1, float(t)) is False

    def test_new_additional_defect_triggers(self):
        p = MofNPolicy(m=3, n=5, disappear_frames=3)
        # First defect triggers alarm
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # baseline=1
        p.reset()

        # Same 1 defect — suppressed
        assert p.update(1, 4.0) is False
        assert p.update(1, 5.0) is False

        # Second defect appears (count=2 > baseline=1) -> triggers
        assert p.update(2, 6.0) is True  # baseline now 2
        p.reset()

        # Both still there — suppressed
        assert p.update(2, 7.0) is False

    def test_disappear_grace_period(self):
        """Defect vanishes for only 2 frames (< disappear_frames=3) then reappears.
        Baseline should NOT clear — still suppressed."""
        p = MofNPolicy(m=3, n=5, disappear_frames=3)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # baseline=1
        p.reset()

        # Brief disappearance: only 2 frames (less than 3)
        assert p.update(0, 4.0) is False
        assert p.update(0, 5.0) is False
        # Reappears before grace expires — baseline still 1, suppressed
        assert p.update(1, 6.0) is False
        assert p.update(1, 7.0) is False
        assert p.update(1, 8.0) is False

    def test_reset_clears_window_not_baseline(self):
        p = MofNPolicy(m=3, n=5)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # baseline=1
        p.reset()
        # After reset, window is clear but baseline survives
        # Same count is still suppressed
        assert not p.update(1, 4.0)
        assert not p.update(1, 5.0)
        assert not p.update(1, 6.0)

    def test_sliding_window(self):
        p = MofNPolicy(m=3, n=5)
        # Fill: 1 1 0 0 0 -> 2 of 5 -> no trigger
        for i, det in enumerate([1, 1, 0, 0, 0]):
            result = p.update(det, float(i))
        assert result is False

        # Add 1 -> window is 1 0 0 0 1 -> 2 of 5 -> no trigger
        assert p.update(1, 5.0) is False
        # Add 1 -> window is 0 0 0 1 1 -> 2 of 5 -> no trigger
        assert p.update(1, 6.0) is False
        # Add 1 -> window is 0 0 1 1 1 -> 3 of 5 -> triggers
        assert p.update(1, 7.0) is True

    def test_partial_disappearance_lowers_baseline(self):
        """Two defects trigger alarm (baseline=2). One disappears for 3 frames
        (count=1). Baseline drops to 1. A new second defect (count=2)
        triggers a fresh alarm."""
        p = MofNPolicy(m=3, n=5, disappear_frames=3)
        # Two defects detected for 3 frames -> alarm
        p.update(2, 1.0)
        p.update(2, 2.0)
        assert p.update(2, 3.0) is True  # baseline=2
        p.reset()

        # One leaves: count drops to 1 for 3 frames
        assert p.update(1, 4.0) is False  # below_run=1
        assert p.update(1, 5.0) is False  # below_run=2
        assert p.update(1, 6.0) is False  # below_run=3 -> baseline drops to 1

        # New second defect appears (count=2 > baseline=1)
        assert p.update(2, 7.0) is True  # new alarm

    def test_partial_disappearance_grace_holds(self):
        """Two defects, one disappears for only 2 frames (< 3). Baseline stays 2,
        so same count=2 coming back is still suppressed."""
        p = MofNPolicy(m=3, n=5, disappear_frames=3)
        p.update(2, 1.0)
        p.update(2, 2.0)
        assert p.update(2, 3.0) is True  # baseline=2
        p.reset()

        # Brief partial disappearance: only 2 frames at count=1
        assert p.update(1, 4.0) is False
        assert p.update(1, 5.0) is False
        # Back to 2 before grace expires — baseline still 2, suppressed
        assert p.update(2, 6.0) is False
        assert p.update(2, 7.0) is False
