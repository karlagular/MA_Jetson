"""Camera adapter: replay from a video file (for testing / validation)."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from ports.camera import CameraPort


class ReplayVideoCamera(CameraPort):
    def __init__(self, video_path: str, loop: bool = False) -> None:
        self._path = video_path
        self._loop = loop
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._path)
        return self._cap.isOpened()

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None:
            return False, None
        ok, frame = self._cap.read()
        if not ok and self._loop:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        return ok, frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
