"""
Pytest configuration for hardware-in-the-loop (HIL) tests.

HIL tests require real hardware (cameras, printers) and are typically slow and
environment-dependent. They are separated from integration tests because:
  1. They cannot run in most CI/CD pipelines without special hardware
  2. They require external dependencies (network, physical devices)
  3. They may have non-deterministic timing

Markers available:
  @pytest.mark.hil_camera       - Tests involving real camera hardware
  @pytest.mark.hil_printer      - Tests involving real printer hardware
  @pytest.mark.hil_full_system  - Full system tests involving multiple components

Run HIL tests:
    pytest tests/integration/hil/
    pytest tests/integration/hil/ -v
    pytest tests/integration/hil/ -m hil_printer   # only printer tests
    pytest tests/integration/hil/ -m "not hil_camera"  # skip camera tests

Skip HIL tests (recommended for CI):
    pytest tests/ --ignore=tests/integration/hil/
    pytest tests/integration/ --ignore=tests/integration/hil/
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    """Add HIL printer/camera options to pytest."""
    parser.addoption("--camera", default="usb",
                     choices=["basler", "usb", "rtsp"],
                     help="Select camera backend (default: usb)")
    parser.addoption("--model-path", default="models_available/yolo11n-seg.pt",
                     help="Path to YOLO model (default: models_available/yolo11n-seg.pt)")
    parser.addoption("--conf", type=float, default=0.5,
                     help="YOLO confidence threshold (default: 0.5)")
    parser.addoption("--max-frames", type=int, default=300,
                     help="Max frames to process (default: 300)")
    parser.addoption("--warmup-frames", type=int, default=5,
                     help="Warmup frames for latency (default: 5)")
    parser.addoption("--display", action="store_true",
                     help="Show live overlay during test")
    parser.addoption("--usb-device", type=int, default=0,
                     help="USB camera device (default: 0)")
    parser.addoption("--usb-width", type=int, default=640,
                     help="USB camera width (default: 640)")
    parser.addoption("--usb-height", type=int, default=480,
                     help="USB camera height (default: 480)")
    parser.addoption("--basler-serial", default=None,
                     help="Basler serial number (optional)")
    parser.addoption("--rtsp-url", default="rtsp://192.168.178.68:8554/cam",
                     help="RTSP URL (default: rtsp://192.168.178.68:8554/cam)")

    parser.addoption("--printer",
                     choices=["Bambulab", "Prusa", "Ultimaker", "RatRig"],
                     help="Printer to test (required for printer HIL tests)")
    parser.addoption("--sequence", default="pause-resume",
                     choices=["pause-resume", "pause-stop", "pause-resume-pause-stop"],
                     help="Command sequence (default: pause-resume)")
    parser.addoption("--machine-config", default="machine_config.json",
                     help="Path to machine_config.json")
    parser.addoption("--skip-connectivity-check", action="store_true",
                     help="Skip initial connectivity check")
    parser.addoption("--yes", action="store_true",
                     help="Auto-confirm prompts (non-interactive)")
    parser.addoption("--log-io", action="store_true",
                     help="Write HIL terminal output and printer TX/RX IO to TXT logs")
    parser.addoption("--log-dir", default="tests_hil_integration/logs",
                     help="Directory for HIL TXT logs (default: tests_hil_integration/logs)")


def pytest_configure(config):
    """Register HIL markers."""
    config.addinivalue_line("markers", "hil_camera: marks tests as requiring real camera hardware")
    config.addinivalue_line("markers", "hil_printer: marks tests as requiring real printer hardware")
    config.addinivalue_line("markers", "hil_full_system: marks tests as requiring full system integration")
