"""Unit tests for BaslerPylonCamera."""

import builtins
import types
from unittest.mock import MagicMock, patch

import numpy as np

from adapters.camera.basler_pypylon import BaslerPylonCamera


def _build_fake_pylon_env(grab_succeeds: bool = True):
    selected_device = MagicMock()
    selected_device.GetSerialNumber.return_value = "SERIAL_A"

    other_device = MagicMock()
    other_device.GetSerialNumber.return_value = "SERIAL_B"

    factory = MagicMock()
    factory.EnumerateDevices.return_value = [selected_device, other_device]
    factory.CreateDevice.side_effect = lambda dev: dev

    cam = MagicMock()
    cam.IsGrabbing.return_value = True
    cam.IsOpen.return_value = True
    cam.GetDeviceInfo.return_value = types.SimpleNamespace(
        GetModelName=lambda: "BaslerModel",
        GetSerialNumber=lambda: "SERIAL_A",
    )

    converter = MagicMock()
    image = MagicMock()
    image.GetArray.return_value = np.zeros((3, 4, 3), dtype=np.uint8)
    converter.Convert.return_value = image

    grab = MagicMock()
    grab.GrabSucceeded.return_value = grab_succeeds
    cam.RetrieveResult.return_value = grab

    fake_pylon = types.SimpleNamespace(
        TlFactory=types.SimpleNamespace(GetInstance=lambda: factory),
        InstantCamera=lambda device: cam,
        ImageFormatConverter=lambda: converter,
        PixelType_BGR8packed=1,
        OutputBitAlignment_MsbAligned=2,
        GrabStrategy_LatestImageOnly=3,
        TimeoutHandling_Return=4,
    )

    return {
        "factory": factory,
        "camera": cam,
        "converter": converter,
        "grab": grab,
        "selected_device": selected_device,
        "other_device": other_device,
        "fake_module": types.SimpleNamespace(pylon=fake_pylon),
    }


class TestBaslerPylonCamera:
    def test_open_returns_false_when_pypylon_missing(self):
        camera = BaslerPylonCamera()
        orig_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "pypylon":
                raise ImportError("missing")
            return orig_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            assert camera.open() is False

    def test_open_returns_false_when_no_devices(self):
        fake = _build_fake_pylon_env()
        fake["factory"].EnumerateDevices.return_value = []

        with patch.dict("sys.modules", {"pypylon": fake["fake_module"]}):
            camera = BaslerPylonCamera()
            assert camera.open() is False

    def test_open_selects_matching_serial(self):
        fake = _build_fake_pylon_env()

        with patch.dict("sys.modules", {"pypylon": fake["fake_module"]}):
            camera = BaslerPylonCamera(serial="SERIAL_B")
            assert camera.open() is True

        fake["factory"].CreateDevice.assert_called_once_with(fake["other_device"])
        fake["camera"].Open.assert_called_once()
        fake["camera"].StartGrabbing.assert_called_once()

    def test_read_frame_success_rotates_and_releases_grab(self):
        fake = _build_fake_pylon_env(grab_succeeds=True)

        with patch.dict("sys.modules", {"pypylon": fake["fake_module"]}):
            with patch("adapters.camera.basler_pypylon.cv2.rotate", side_effect=lambda f, _: f) as mock_rotate:
                camera = BaslerPylonCamera()
                assert camera.open() is True
                ok, frame = camera.read_frame()

        assert ok is True
        assert frame is not None
        mock_rotate.assert_called_once()
        fake["grab"].Release.assert_called_once()

    def test_read_frame_failure_releases_grab(self):
        fake = _build_fake_pylon_env(grab_succeeds=False)

        with patch.dict("sys.modules", {"pypylon": fake["fake_module"]}):
            camera = BaslerPylonCamera()
            assert camera.open() is True
            ok, frame = camera.read_frame()

        assert ok is False
        assert frame is None
        fake["grab"].Release.assert_called_once()

    def test_read_frame_when_camera_not_grabbing(self):
        fake = _build_fake_pylon_env(grab_succeeds=True)
        fake["camera"].IsGrabbing.return_value = False

        with patch.dict("sys.modules", {"pypylon": fake["fake_module"]}):
            camera = BaslerPylonCamera()
            assert camera.open() is True
            ok, frame = camera.read_frame()

        assert ok is False
        assert frame is None

    def test_close_stops_grabbing_and_closes(self):
        fake = _build_fake_pylon_env()

        with patch.dict("sys.modules", {"pypylon": fake["fake_module"]}):
            camera = BaslerPylonCamera()
            assert camera.open() is True
            camera.close()
            camera.close()

        fake["camera"].StopGrabbing.assert_called_once()
        fake["camera"].Close.assert_called_once()
