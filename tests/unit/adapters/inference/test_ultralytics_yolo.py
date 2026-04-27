"""
Unit tests for adapters.inference.ultralytics_yolo.UltralyticsYOLO.

Verifies the Ultralytics YOLO inference adapter using a mocked YOLO model
so no model weights file or GPU is required.

Coverage:
  - Device selection: uses "cuda" when torch.cuda.is_available() is True,
    falls back to "cpu" otherwise.
  - predict() with no boxes returns an empty DetectionResult
    (defect_detected=False, defect_count=0).
  - predict() correctly extracts bounding boxes, class names, and counts
    the number of "defect" detections.
  - Segmentation masks are extracted and converted to numpy arrays when
    present in the model output.

Usage:
    pytest tests/unit/adapters/inference/test_ultralytics_yolo.py
    pytest tests/unit/adapters/inference/test_ultralytics_yolo.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from adapters.inference.ultralytics_yolo import UltralyticsYOLO


class _FakeMaskTensor:
    def __init__(self, arr):
        self._arr = arr

    def cpu(self):
        return self

    def numpy(self):
        return self._arr


class TestUltralyticsYOLO:
    def test_init_uses_cuda_when_available(self):
        model = MagicMock()
        with patch("adapters.inference.ultralytics_yolo.torch.cuda.is_available", return_value=True):
            with patch("adapters.inference.ultralytics_yolo.YOLO", return_value=model):
                adapter = UltralyticsYOLO("model.pt")

        assert adapter._device == "cuda"

    def test_init_uses_cpu_when_cuda_unavailable(self):
        model = MagicMock()
        with patch("adapters.inference.ultralytics_yolo.torch.cuda.is_available", return_value=False):
            with patch("adapters.inference.ultralytics_yolo.YOLO", return_value=model):
                adapter = UltralyticsYOLO("model.pt")

        assert adapter._device == "cpu"

    def test_predict_no_boxes_returns_empty_result(self):
        model = MagicMock()
        result = SimpleNamespace(boxes=None, names={})
        model.predict.return_value = [result]

        with patch("adapters.inference.ultralytics_yolo.torch.cuda.is_available", return_value=False):
            with patch("adapters.inference.ultralytics_yolo.YOLO", return_value=model):
                adapter = UltralyticsYOLO("model.pt")
                out = adapter.predict(np.zeros((4, 4, 3), dtype=np.uint8))

        assert out.boxes == []
        assert out.masks is None
        assert out.defect_detected is False
        assert out.defect_count == 0

    def test_predict_extracts_boxes_and_defect_count(self):
        box1 = SimpleNamespace(
            xyxy=[np.array([1, 2, 11, 12])],
            conf=[np.array(0.9)],
            cls=[np.array(0)],
        )
        box2 = SimpleNamespace(
            xyxy=[np.array([5, 6, 15, 16])],
            conf=[np.array(0.4)],
            cls=[np.array(1)],
        )
        result = SimpleNamespace(
            boxes=[box1, box2],
            names={0: "defect", 1: "cat"},
            masks=None,
        )

        model = MagicMock()
        model.predict.return_value = [result]

        with patch("adapters.inference.ultralytics_yolo.torch.cuda.is_available", return_value=False):
            with patch("adapters.inference.ultralytics_yolo.YOLO", return_value=model):
                adapter = UltralyticsYOLO("model.pt")
                out = adapter.predict(np.zeros((8, 8, 3), dtype=np.uint8))

        assert len(out.boxes) == 2
        assert out.boxes[0].x1 == 1
        assert out.boxes[0].y2 == 12
        assert out.defect_detected is True
        assert out.defect_count == 1
        assert out.class_names == {0: "defect", 1: "cat"}

    def test_safe_class_is_not_counted_as_defect(self):
        """Detection of the safe class ID must not increment defect_count."""
        box_safe = SimpleNamespace(
            xyxy=[np.array([0, 0, 4, 4])],
            conf=[np.array(0.95)],
            cls=[np.array(2)],
        )
        result = SimpleNamespace(
            boxes=[box_safe],
            names={2: "background"},
            masks=None,
        )
        model = MagicMock()
        model.predict.return_value = [result]

        with patch("adapters.inference.ultralytics_yolo.torch.cuda.is_available", return_value=False):
            with patch("adapters.inference.ultralytics_yolo.YOLO", return_value=model):
                adapter = UltralyticsYOLO("model.pt", safe_class_id=2)
                out = adapter.predict(np.zeros((8, 8, 3), dtype=np.uint8))

        assert out.defect_detected is False
        assert out.defect_count == 0

    def test_non_safe_class_is_counted_as_defect(self):
        """Only detections whose class ID differs from safe_class_id count as defects."""
        box_safe = SimpleNamespace(
            xyxy=[np.array([0, 0, 4, 4])],
            conf=[np.array(0.9)],
            cls=[np.array(1)],
        )
        box_defect = SimpleNamespace(
            xyxy=[np.array([5, 5, 9, 9])],
            conf=[np.array(0.85)],
            cls=[np.array(0)],
        )
        result = SimpleNamespace(
            boxes=[box_safe, box_defect],
            names={0: "crack", 1: "background"},
            masks=None,
        )
        model = MagicMock()
        model.predict.return_value = [result]

        with patch("adapters.inference.ultralytics_yolo.torch.cuda.is_available", return_value=False):
            with patch("adapters.inference.ultralytics_yolo.YOLO", return_value=model):
                adapter = UltralyticsYOLO("model.pt", safe_class_id=1)
                out = adapter.predict(np.zeros((8, 8, 3), dtype=np.uint8))

        assert out.defect_detected is True
        assert out.defect_count == 1

    def test_predict_collects_masks_when_present(self):
        box = SimpleNamespace(
            xyxy=[np.array([0, 0, 2, 2])],
            conf=[np.array(0.8)],
            cls=[np.array(0)],
        )
        mask_arr = np.ones((2, 2), dtype=np.float32)
        masks = [SimpleNamespace(data=[_FakeMaskTensor(mask_arr)])]
        result = SimpleNamespace(
            boxes=[box],
            names={0: "defect"},
            masks=masks,
        )

        model = MagicMock()
        model.predict.return_value = [result]

        with patch("adapters.inference.ultralytics_yolo.torch.cuda.is_available", return_value=False):
            with patch("adapters.inference.ultralytics_yolo.YOLO", return_value=model):
                adapter = UltralyticsYOLO("model.pt")
                out = adapter.predict(np.zeros((8, 8, 3), dtype=np.uint8))

        assert out.masks is not None
        assert len(out.masks) == 1
        assert np.array_equal(out.masks[0], mask_arr)
