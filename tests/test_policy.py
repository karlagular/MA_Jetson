"""Unit tests for domain.policy — MofNPolicy."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.policy import MofNPolicy


class TestMofNPolicy:
    def test_does_not_trigger_below_threshold(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
        # Only 2 detections in 5 frames -> no trigger
        assert not p.update(1, 1.0)
        assert not p.update(1, 2.0)
        assert not p.update(0, 3.0)
        assert not p.update(0, 4.0)
        assert not p.update(0, 5.0)

    def test_triggers_at_threshold(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
        p.update(1, 1.0)
        p.update(1, 2.0)
        result = p.update(1, 3.0)
        assert result is True

    def test_cooldown_prevents_retrigger(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=10.0)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # triggers

        # Baseline is now 1 — same count is suppressed regardless of cooldown
        p.reset()  # simulate alarm dismissal
        p.update(1, 4.0)
        assert p.update(1, 5.0) is False

    def test_triggers_again_after_disappearance(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0, disappear_frames=3)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # triggers, baseline=1
        p.reset()

        # Person still visible — suppressed
        assert p.update(1, 4.0) is False
        assert p.update(1, 5.0) is False

        # Person disappears for 3 consecutive frames -> baseline clears
        assert p.update(0, 6.0) is False
        assert p.update(0, 7.0) is False
        assert p.update(0, 8.0) is False  # zero_run=3, baseline reset to 0

        # Re-detect: need M detections again to trigger
        p.update(1, 9.0)
        p.update(1, 10.0)
        assert p.update(1, 11.0) is True  # new alarm

    def test_same_person_suppressed_after_dismissal(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0, disappear_frames=3)
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # triggers, baseline=1
        p.reset()

        # Same person stays — never re-triggers
        for t in range(4, 20):
            assert p.update(1, float(t)) is False

    def test_new_additional_person_triggers(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0, disappear_frames=3)
        # First person triggers alarm
        p.update(1, 1.0)
        p.update(1, 2.0)
        assert p.update(1, 3.0) is True  # baseline=1
        p.reset()

        # Same 1 person — suppressed
        assert p.update(1, 4.0) is False
        assert p.update(1, 5.0) is False

        # Second person appears (count=2 > baseline=1) -> triggers
        assert p.update(2, 6.0) is True  # baseline now 2
        p.reset()

        # Both still there — suppressed
        assert p.update(2, 7.0) is False

    def test_disappear_grace_period(self):
        """Person vanishes for only 2 frames (< disappear_frames=3) then reappears.
        Baseline should NOT clear — still suppressed."""
        p = MofNPolicy(m=3, n=5, cooldown_s=0, disappear_frames=3)
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
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
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
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
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
