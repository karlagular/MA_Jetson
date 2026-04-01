"""Unit tests for domain.policy — MofNPolicy."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.policy import MofNPolicy


class TestMofNPolicy:
    def test_does_not_trigger_below_threshold(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
        # Only 2 detections in 5 frames -> no trigger
        assert not p.update(True, 1.0)
        assert not p.update(True, 2.0)
        assert not p.update(False, 3.0)
        assert not p.update(False, 4.0)
        assert not p.update(False, 5.0)

    def test_triggers_at_threshold(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
        p.update(True, 1.0)
        p.update(True, 2.0)
        result = p.update(True, 3.0)
        assert result is True

    def test_cooldown_prevents_retrigger(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=10.0)
        p.update(True, 1.0)
        p.update(True, 2.0)
        assert p.update(True, 3.0) is True  # triggers

        # Within cooldown -> no trigger even if M detections
        p.update(True, 4.0)
        assert p.update(True, 5.0) is False

    def test_triggers_again_after_cooldown(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=5.0)
        p.update(True, 1.0)
        p.update(True, 2.0)
        assert p.update(True, 3.0) is True  # triggers, last_trigger=3.0

        # Insert no-detections to flush window, then re-detect past cooldown
        p.update(False, 4.0)
        p.update(False, 5.0)
        p.update(False, 6.0)
        p.update(False, 7.0)
        p.update(False, 8.0)  # window now [F, F, F, F, F]

        # Past cooldown (>8.0), build up M detections again
        p.update(True, 9.0)
        p.update(True, 10.0)
        assert p.update(True, 11.0) is True  # 3 of 5, cooldown elapsed

    def test_reset_clears_state(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
        p.update(True, 1.0)
        p.update(True, 2.0)
        p.reset()
        # After reset, need 3 fresh detections
        assert not p.update(True, 3.0)
        assert not p.update(True, 4.0)
        assert p.update(True, 5.0) is True

    def test_sliding_window(self):
        p = MofNPolicy(m=3, n=5, cooldown_s=0)
        # Fill: True True False False False -> 2 of 5 -> no trigger
        for i, det in enumerate([True, True, False, False, False]):
            result = p.update(det, float(i))
        assert result is False

        # Add True -> window is True False False False True -> 2 of 5 -> no trigger
        assert p.update(True, 5.0) is False
        # Add True -> window is False False False True True -> 2 of 5 -> no trigger
        assert p.update(True, 6.0) is False
        # Add True -> window is False False True True True -> 3 of 5 -> triggers
        assert p.update(True, 7.0) is True
