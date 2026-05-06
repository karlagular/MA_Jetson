"""
Unit tests for adapters.logging.jsonl_logger.JsonlLogger.

Verifies the JSONL-based event logger that persists alarm events, frame
snapshots, and latency measurements to disk.

Coverage:
  - __init__ creates the session directory and sets the events file path.
  - log_alarm appends one JSON line per AlarmEvent to events.jsonl.
  - save_frame calls cv2.imwrite with the correct path and frame data.
  - save_latency_log writes a CSV-style header + one row per record to
    latency_log.txt.

Tests use pytest's tmp_path fixture; cv2.imwrite is patched so no display
or filesystem write to /tmp is needed beyond text files.

Usage:
    pytest tests/unit/adapters/logging/test_jsonl_logger.py
    pytest tests/unit/adapters/logging/test_jsonl_logger.py -v
"""

import json
from unittest.mock import patch

import numpy as np

from adapters.logging.jsonl_logger import JsonlLogger
from domain.models import AlarmEvent, BBox


class TestJsonlLogger:
    def test_init_creates_session_dir(self, tmp_path):
        session_dir = tmp_path / "session"
        logger = JsonlLogger(str(session_dir))
        assert session_dir.exists()
        assert logger._events_path.endswith("events.jsonl")

    def test_log_alarm_appends_jsonl(self, tmp_path):
        logger = JsonlLogger(str(tmp_path))

        event = AlarmEvent(
            timestamp="2026-01-01T00:00:00",
            frame_index=5,
            state_from="A",
            state_to="B",
            action="continue",
        )
        logger.log_alarm(event)
        logger.log_alarm(event)

        content = (tmp_path / "events.jsonl").read_text().splitlines()
        assert len(content) == 2
        parsed = json.loads(content[0])
        assert parsed["frame_index"] == 5
        assert parsed["action"] == "continue"

    def test_save_frame_calls_cv2_imwrite(self, tmp_path):
        logger = JsonlLogger(str(tmp_path))
        frame = np.zeros((5, 5, 3), dtype=np.uint8)

        with patch("adapters.logging.jsonl_logger.cv2.imwrite", return_value=True) as mock_imwrite:
            logger.save_frame(frame, "alarm_001")

        path_arg = mock_imwrite.call_args[0][0]
        assert path_arg.endswith("alarm_001.jpg")
        assert np.array_equal(mock_imwrite.call_args[0][1], frame)

    def test_save_latency_log_writes_header_and_rows(self, tmp_path):
        logger = JsonlLogger(str(tmp_path))
        records = [
            (1, 1.1, 2.2, 3.3, 4.4, 5.5, 16.5),
            (2, 0.1, 0.2, 0.3, 0.4, 0.5, 1.5),
        ]

        logger.save_latency_log(records)

        lines = (tmp_path / "latency_log.txt").read_text().splitlines()
        assert lines[0] == "frame,capture_ms,inference_ms,postprocess_ms,policy_ms,display_ms,total_ms"
        assert lines[1].startswith("1,1.100,2.200")
        assert lines[2].startswith("2,0.100,0.200")

    def test_save_run_summary_persists_alarm_policy_params(self, tmp_path):
        logger = JsonlLogger(
            str(tmp_path),
            alarm_m=7,
            alarm_n=11,
            alarm_disappear_frames=13,
            inference_conf=0.65,
        )

        logger.save_run_summary(frame_count=42, alarms_activated=3)

        summary = json.loads((tmp_path / "summary.json").read_text())
        assert summary["frame_count"] == 42
        assert summary["alarms_activated"] == 3
        assert summary["alarm_m"] == 7
        assert summary["alarm_n"] == 11
        assert summary["alarm_disappear_frames"] == 13
        assert summary["inference_conf"] == 0.65

    def test_save_bboxes_persists_inference_output_json(self, tmp_path):
        logger = JsonlLogger(str(tmp_path))
        boxes = [
            BBox(x1=10, y1=20, x2=30, y2=40, conf=0.91, cls_id=2, cls_name="blob"),
            BBox(x1=11, y1=21, x2=31, y2=41, conf=0.55, cls_id=3, cls_name="scratch"),
        ]

        logger.save_bboxes(boxes, "alarm_boxes")

        payload = json.loads((tmp_path / "alarm_boxes.json").read_text())
        assert len(payload) == 2
        assert payload[0]["x1"] == 10
        assert payload[0]["conf"] == 0.91
        assert payload[1]["cls_name"] == "scratch"
