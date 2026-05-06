from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption(
        "--system-camera",
        default="basler",
        choices=["basler", "usb", "rtsp", "replay"],
        help="Camera backend for system test (default: basler)",
    )
    parser.addoption(
        "--system-basler-serial",
        default=None,
        help="Optional Basler serial number",
    )
    parser.addoption("--system-usb-device", type=int, default=0, help="USB camera device id")
    parser.addoption("--system-usb-width", type=int, default=640, help="USB camera frame width")
    parser.addoption("--system-usb-height", type=int, default=480, help="USB camera frame height")
    parser.addoption(
        "--system-rtsp-url",
        default="rtsp://10.0.0.5:8554/cam",
        help="RTSP URL when --system-camera=rtsp",
    )
    parser.addoption(
        "--system-video-path",
        default="",
        help="Replay video path when --system-camera=replay",
    )
    parser.addoption(
        "--system-model-path",
        default="models_available/best.pt",
        help="YOLO model path",
    )
    parser.addoption("--system-conf", type=float, default=0.5, help="YOLO confidence threshold")
    parser.addoption(
        "--system-safe-class-id",
        type=int,
        default=0,
        help="Safe class id for defect filtering (default: 0)",
    )
    parser.addoption("--system-alarm-m", "--m", type=int, default=3, help="Alarm M in M-of-N")
    parser.addoption("--system-alarm-n", "--n", type=int, default=5, help="Alarm N in M-of-N")
    parser.addoption(
        "--system-alarm-disappear-frames",
        "--d",
        type=int,
        default=30,
        help="Disappear-frame count (D) used by M-of-N suppression logic",
    )
    parser.addoption(
        "--system-continue-delay-s",
        type=float,
        default=1.0,
        help="Seconds to wait before auto-continue after alarm enable",
    )
    parser.addoption(
        "--system-log-dir",
        default="System_Test/logs",
        help="Base directory for per-run log folders",
    )
