"""Pure helper functions used inside the pipeline."""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

from domain.models import BBox, DetectionResult


def draw_overlay(
    frame: np.ndarray,
    result: DetectionResult,
    colors: List[Tuple[int, int, int]],
    alpha: float = 0.3,
) -> np.ndarray:
    """Draw masks, boxes, and labels onto a *copy* of *frame*."""
    out = frame.copy()

    if result.masks is not None:
        for mask, box in zip(result.masks, result.boxes):
            color = colors[box.cls_id % len(colors)]
            out = _draw_mask(out, mask, color, alpha)

    for box in result.boxes:
        color = colors[box.cls_id % len(colors)]
        _draw_box(out, box, color)

    return out


def resize_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    return cv2.resize(frame, (width, height))


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _draw_mask(
    img: np.ndarray, mask: np.ndarray, color: Tuple[int, int, int], alpha: float
) -> np.ndarray:
    overlay = img.copy()
    if mask.shape[:2] != img.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    bool_mask = mask.astype(bool)
    overlay[bool_mask] = color
    return cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)


def _draw_box(img: np.ndarray, box: BBox, color: Tuple[int, int, int]) -> None:
    cv2.rectangle(img, (box.x1, box.y1), (box.x2, box.y2), color, 2)
    label = f"{box.cls_name} {box.conf:.2f}"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
    cv2.rectangle(img, (box.x1, box.y1 - th - 8), (box.x1 + tw, box.y1), color, -1)
    cv2.putText(img, label, (box.x1, box.y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
