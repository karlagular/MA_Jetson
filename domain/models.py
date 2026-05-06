"""Domain value objects shared across the system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float
    cls_id: int
    cls_name: str


@dataclass
class DetectionResult:
    boxes: List[BBox] = field(default_factory=list)
    masks: Optional[List[np.ndarray]] = None
    defect_detected: bool = False
    defect_count: int = 0
    class_names: Dict[int, str] = field(default_factory=dict)


@dataclass
class FramePacket:
    frame: np.ndarray
    index: int
    timestamp_ns: int
    raw_frame: Optional[np.ndarray] = None
    mask_frame: Optional[np.ndarray] = None


@dataclass
class AlarmEvent:
    timestamp: str
    frame_index: int
    state_from: str
    state_to: str
    action: str
