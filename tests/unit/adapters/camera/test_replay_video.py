"""Unit tests for ReplayVideoCamera."""

from unittest.mock import MagicMock, call, patch

import numpy as np

from adapters.camera.replay_video import ReplayVideoCamera


class TestReplayVideoCamera:
    def test_open_failure(self):
        cap = MagicMock()
        cap.isOpened.return_value = False

        with patch("adapters.camera.replay_video.cv2.VideoCapture", return_value=cap):
            camera = ReplayVideoCamera("missing.mp4")
            assert camera.open() is False

    def test_read_frame_success(self):
        frame = np.zeros((5, 5, 3), dtype=np.uint8)
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, frame)

        with patch("adapters.camera.replay_video.cv2.VideoCapture", return_value=cap):
            camera = ReplayVideoCamera("ok.mp4")
            camera.open()
            ok, out = camera.read_frame()

        assert ok is True
        assert out is frame

    def test_read_eof_without_loop(self):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)

        with patch("adapters.camera.replay_video.cv2.VideoCapture", return_value=cap):
            camera = ReplayVideoCamera("video.mp4", loop=False)
            camera.open()
            ok, frame = camera.read_frame()

        assert ok is False
        assert frame is None
        cap.set.assert_not_called()

    def test_read_eof_with_loop_rewinds_and_retries(self):
        frame = np.ones((4, 4, 3), dtype=np.uint8)
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.side_effect = [(False, None), (True, frame)]

        with patch("adapters.camera.replay_video.cv2.VideoCapture", return_value=cap):
            camera = ReplayVideoCamera("video.mp4", loop=True)
            camera.open()
            ok, out = camera.read_frame()

        assert ok is True
        assert out is frame
        cap.set.assert_called_once()

    def test_close_releases_capture(self):
        cap = MagicMock()
        cap.isOpened.return_value = True

        with patch("adapters.camera.replay_video.cv2.VideoCapture", return_value=cap):
            camera = ReplayVideoCamera("video.mp4")
            camera.open()
            camera.close()

        cap.release.assert_called_once()
