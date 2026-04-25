"""Port: object-detection / segmentation inference."""

from abc import ABC, abstractmethod

import numpy as np

from domain.models import DetectionResult


class InferencePort(ABC):
    @abstractmethod
    def predict(self, frame: np.ndarray) -> DetectionResult:
        """Run inference on a single frame."""
