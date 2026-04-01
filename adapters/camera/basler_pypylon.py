"""Camera adapter: Basler USB camera via pypylon."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from ports.camera import CameraPort


class BaslerPylonCamera(CameraPort):
    def __init__(self, serial: Optional[str] = None) -> None:
        self._serial = serial
        self._camera = None
        self._converter = None

    def open(self) -> bool:
        try:
            from pypylon import pylon
        except ImportError:
            print("ERROR: pypylon is not installed. Run: pip install pypylon")
            return False

        factory = pylon.TlFactory.GetInstance()
        devices = factory.EnumerateDevices()
        if not devices:
            print("ERROR: No Basler camera detected.")
            return False

        selected = devices[0]
        if self._serial:
            for dev in devices:
                if dev.GetSerialNumber() == self._serial:
                    selected = dev
                    break

        self._camera = pylon.InstantCamera(factory.CreateDevice(selected))
        self._camera.Open()

        self._converter = pylon.ImageFormatConverter()
        self._converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self._converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        info = self._camera.GetDeviceInfo()
        print(f"[Basler] Opened {info.GetModelName()} serial={info.GetSerialNumber()}")
        return True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._camera is None or not self._camera.IsGrabbing():
            return False, None
        from pypylon import pylon

        grab = self._camera.RetrieveResult(3000, pylon.TimeoutHandling_Return)
        if grab is None or not grab.GrabSucceeded():
            if grab is not None:
                grab.Release()
            return False, None

        image = self._converter.Convert(grab)
        frame = image.GetArray()
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        grab.Release()
        return True, frame

    def close(self) -> None:
        if self._camera is not None:
            if self._camera.IsGrabbing():
                self._camera.StopGrabbing()
            if self._camera.IsOpen():
                self._camera.Close()
            self._camera = None
