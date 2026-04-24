"""Unit tests for RTSPGStreamerCamera."""

from unittest.mock import MagicMock, patch

import numpy as np

from adapters.camera.rtsp_gstreamer import RTSPGStreamerCamera


class TestRTSPGStreamerCamera:
    def test_open_success_uses_gstreamer_backend(self):
        cap = MagicMock()
        cap.isOpened.return_value = True

        with patch("adapters.camera.rtsp_gstreamer.cv2.VideoCapture", return_value=cap) as mock_vc:
            camera = RTSPGStreamerCamera("pipeline-string")
            assert camera.open() is True

        args, _ = mock_vc.call_args
        assert args[0] == "pipeline-string"
        assert args[1] is not None

    def test_open_failure(self):
        cap = MagicMock()
        cap.isOpened.return_value = False

        with patch("adapters.camera.rtsp_gstreamer.cv2.VideoCapture", return_value=cap):
            camera = RTSPGStreamerCamera("bad-pipeline")
            assert camera.open() is False

    def test_read_frame_success(self):
        frame = np.ones((8, 8, 3), dtype=np.uint8)
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, frame)

        with patch("adapters.camera.rtsp_gstreamer.cv2.VideoCapture", return_value=cap):
            camera = RTSPGStreamerCamera("pipeline")
            camera.open()
            ok, out = camera.read_frame()

        assert ok is True
        assert out is frame

    def test_read_frame_when_not_open(self):
        camera = RTSPGStreamerCamera("pipeline")
        ok, frame = camera.read_frame()
        assert ok is False
        assert frame is None

    def test_close_releases_capture(self):
        cap = MagicMock()
        cap.isOpened.return_value = True

        with patch("adapters.camera.rtsp_gstreamer.cv2.VideoCapture", return_value=cap):
            camera = RTSPGStreamerCamera("pipeline")
            camera.open()
            camera.close()

        cap.release.assert_called_once()
