"""Camera adapter: OpenCV USB webcam."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from ports.camera import CameraPort


class OpenCVUSBCamera(CameraPort):
    def __init__(self, device_id: int = 0, width: int = 640, height: int = 480) -> None:
        self._device_id = device_id
        self._width = width
        self._height = height
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self._device_id)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        return self._cap.isOpened()

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None:
            return False, None
        return self._cap.read()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
