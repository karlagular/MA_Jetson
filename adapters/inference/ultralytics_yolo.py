"""Inference adapter: Ultralytics YOLO (detection + segmentation)."""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import torch
from ultralytics import YOLO

from domain.models import BBox, DetectionResult
from ports.inference import InferencePort


class UltralyticsYOLO(InferencePort):
    def __init__(self, model_path: str, conf: float = 0.5) -> None:
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[YOLO] Using device: {self._device}")
        self._model = YOLO(model_path)
        self._conf = conf

    def predict(self, frame: np.ndarray) -> DetectionResult:
        results = self._model.predict(
            source=frame,
            conf=self._conf,
            device=self._device,
            verbose=False,
        )[0]

        boxes: List[BBox] = []
        masks: Optional[List[np.ndarray]] = None
        person_detected = False
        person_count = 0

        if results.boxes is not None:
            has_masks = hasattr(results, "masks") and results.masks is not None
            if has_masks:
                masks = []

            for i, box in enumerate(results.boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = results.names[cls_id]

                boxes.append(BBox(x1=x1, y1=y1, x2=x2, y2=y2, conf=conf, cls_id=cls_id, cls_name=cls_name))

                if has_masks:
                    masks.append(results.masks[i].data[0].cpu().numpy())

                if cls_name == "person":
                    person_detected = True
                    person_count += 1

        return DetectionResult(
            boxes=boxes,
            masks=masks,
            person_detected=person_detected,
            person_count=person_count,
            class_names=dict(results.names) if results.names else {},
        )
