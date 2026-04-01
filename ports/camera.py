"""Port: camera frame source."""

from abc import ABC, abstractmethod
from typing import Optional, Tuple

import numpy as np


class CameraPort(ABC):
    @abstractmethod
    def open(self) -> bool:
        """Open the camera. Returns True on success."""

    @abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Grab the next frame. Returns (success, frame_or_None)."""

    @abstractmethod
    def close(self) -> None:
        """Release camera resources."""
