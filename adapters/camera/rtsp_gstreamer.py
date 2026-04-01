"""Camera adapter: RTSP stream via GStreamer pipeline."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from ports.camera import CameraPort


class RTSPGStreamerCamera(CameraPort):
    def __init__(self, pipeline: str) -> None:
        self._pipeline = pipeline
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._pipeline, cv2.CAP_GSTREAMER)
        return self._cap.isOpened()

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None:
            return False, None
        return self._cap.read()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
