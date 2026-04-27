"""Inference adapter: deterministic stub for testing."""

from __future__ import annotations

from typing import Dict, Set

import numpy as np

from domain.models import BBox, DetectionResult
from ports.inference import InferencePort


class StubDetections(InferencePort):
    """Returns a fixed defect detection at specified frame indices.

    Useful for unit / integration tests where real model inference is
    not needed.
    """

    def __init__(self, defect_at_frames: Set[int] | None = None) -> None:
        self._defect_frames = defect_at_frames or set()
        self._frame_count = 0

    def predict(self, frame: np.ndarray) -> DetectionResult:
        idx = self._frame_count
        self._frame_count += 1

        if idx in self._defect_frames:
            box = BBox(x1=100, y1=100, x2=200, y2=300, conf=0.95, cls_id=0, cls_name="defect")
            return DetectionResult(
                boxes=[box],
                masks=None,
                defect_detected=True,
                defect_count=1,
                class_names={0: "defect"},
            )

        return DetectionResult(defect_detected=False, class_names={0: "defect"})
 