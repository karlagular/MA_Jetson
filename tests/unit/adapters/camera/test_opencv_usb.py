"""
Unit tests for adapters.camera.opencv_usb.OpenCVUSBCamera.

Verifies the OpenCV USB camera adapter using a mocked cv2.VideoCapture so
no physical camera is required:
  - open() sets the requested resolution via CAP_PROP_FRAME_WIDTH/HEIGHT.
  - open() returns False when the device cannot be opened.
  - read_frame() returns the frame on success and (False, None) before open.
  - close() releases the capture handle and is safely idempotent.

Usage:
    pytest tests/unit/adapters/camera/test_opencv_usb.py
    pytest tests/unit/adapters/camera/test_opencv_usb.py -v
"""

from unittest.mock import MagicMock, patch

import numpy as np

from adapters.camera.opencv_usb import OpenCVUSBCamera


class TestOpenCVUSBCamera:
    def test_open_success_sets_resolution(self):
        cap = MagicMock()
        cap.isOpened.return_value = True

        with patch("adapters.camera.opencv_usb.cv2.VideoCapture", return_value=cap) as mock_vc:
            camera = OpenCVUSBCamera(device_id=2, width=800, height=600)
            assert camera.open() is True

        mock_vc.assert_called_once_with(2)
        cap.set.assert_any_call(3, 800)  # CAP_PROP_FRAME_WIDTH
        cap.set.assert_any_call(4, 600)  # CAP_PROP_FRAME_HEIGHT

    def test_open_failure(self):
        cap = MagicMock()
        cap.isOpened.return_value = False

        with patch("adapters.camera.opencv_usb.cv2.VideoCapture", return_value=cap):
            camera = OpenCVUSBCamera()
            assert camera.open() is False

    def test_read_frame_success(self):
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, frame)

        with patch("adapters.camera.opencv_usb.cv2.VideoCapture", return_value=cap):
            camera = OpenCVUSBCamera()
            camera.open()
            ok, out = camera.read_frame()

        assert ok is True
        assert out is frame

    def test_read_frame_when_not_open(self):
        camera = OpenCVUSBCamera()
        ok, frame = camera.read_frame()
        assert ok is False
        assert frame is None

    def test_close_releases_capture_and_is_idempotent(self):
        cap = MagicMock()
        cap.isOpened.return_value = True

        with patch("adapters.camera.opencv_usb.cv2.VideoCapture", return_value=cap):
            camera = OpenCVUSBCamera()
            camera.open()
            camera.close()
            camera.close()

        cap.release.assert_called_once()
