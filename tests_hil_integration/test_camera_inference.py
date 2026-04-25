"""
Hardware-in-the-loop test: real camera + real YOLO inference.

Tests the complete pipeline from real camera frame capture through YOLO
inference and detects person instances. Supports multiple camera backends:
  - Basler pypylon
  - OpenCV USB
  - GStreamer RTSP

This test is slow and requires a real camera to be connected. It performs
frame capture, inference latency measurement, and console reporting.

Markers: @pytest.mark.hil_camera

Usage:
    pytest tests/integration/hil/test_camera_inference.py
    pytest tests/integration/hil/test_camera_inference.py -v
    pytest tests/integration/hil/test_camera_inference.py --camera=usb --max-frames=50

Command-line options (via pytest --camera, etc.):
    --camera          : Camera backend: basler, usb, or rtsp (default: usb)
    --model-path      : Path to YOLO model (default: models_available/yolo11n-seg.pt)
    --conf            : YOLO confidence threshold (default: 0.5)
    --max-frames      : Max frames to capture (default: 300)
    --warmup-frames   : Frames to exclude from latency stats (default: 5)
    --display         : Show live overlay during test (default: False)
    --usb-device      : USB camera device ID (default: 0)
    --usb-width       : USB camera width (default: 640)
    --usb-height      : USB camera height (default: 480)
    --basler-serial   : Basler serial number (optional)
    --rtsp-url        : RTSP stream URL (default: rtsp://192.168.178.68:8554/cam)
"""

from __future__ import annotations

import pytest
import time
from pathlib import Path
from statistics import mean
from typing import Any

import cv2
import numpy as np

from adapters.camera.basler_pypylon import BaslerPylonCamera
from adapters.camera.opencv_usb import OpenCVUSBCamera
from adapters.camera.rtsp_gstreamer import RTSPGStreamerCamera
from adapters.inference.ultralytics_yolo import UltralyticsYOLO
from pipeline.steps import draw_overlay


def _build_rtsp_pipeline(rtsp_url: str) -> str:
    """Build GStreamer pipeline string for RTSP decoding."""
    return (
        f"rtspsrc location={rtsp_url} latency=200 ! "
        "rtph264depay ! h264parse ! nvv4l2decoder ! "
        "nvvidconv ! video/x-raw,format=BGRx ! "
        "videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
    )


def pytest_addoption(parser):
    """Add HIL-specific options to pytest."""
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


@pytest.fixture
def hil_camera(request):
    """Build and return the selected camera instance."""
    camera_type = request.config.getoption("--camera")
    if camera_type == "basler":
        return BaslerPylonCamera(serial=request.config.getoption("--basler-serial"))
    elif camera_type == "rtsp":
        pipeline = _build_rtsp_pipeline(request.config.getoption("--rtsp-url"))
        return RTSPGStreamerCamera(pipeline)
    else:  # usb
        return OpenCVUSBCamera(
            device_id=request.config.getoption("--usb-device"),
            width=request.config.getoption("--usb-width"),
            height=request.config.getoption("--usb-height"),
        )


@pytest.fixture
def hil_model(request):
    """Load and return YOLO model."""
    return UltralyticsYOLO(
        request.config.getoption("--model-path"),
        conf=request.config.getoption("--conf"),
    )


@pytest.mark.hil_camera
def test_camera_inference(hil_camera, hil_model, request):
    """
    Test real camera capture -> YOLO inference pipeline.
    
    Verifies:
      - Camera opens successfully
      - Frames are captured and passed to inference
      - Person detection latency is measured
      - Inference completes for max_frames or until stream ends
    """
    max_frames = request.config.getoption("--max-frames")
    warmup_frames = request.config.getoption("--warmup-frames")
    display = request.config.getoption("--display")
    
    assert hil_camera.open(), "Camera open failed"
    
    frame_idx = 0
    person_frames = 0
    latencies_ms = []
    colors = [[0, 255, 0], [0, 180, 255], [255, 200, 0], [255, 0, 0]]
    
    try:
        while frame_idx < max_frames:
            ok, frame = hil_camera.read_frame()
            if not ok or frame is None:
                break
            
            t0 = time.perf_counter()
            result = hil_model.predict(frame)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            
            if frame_idx >= warmup_frames:
                latencies_ms.append(dt_ms)
            
            if result.person_count > 0:
                person_frames += 1
            
            if display:
                overlay = draw_overlay(frame, result, colors)
                cv2.putText(overlay, f"frame={frame_idx} persons={result.person_count}",
                           (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.imshow("HIL Camera->Inference", overlay)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            
            frame_idx += 1
    finally:
        hil_camera.close()
        if display:
            cv2.destroyAllWindows()
    
    # Assertions
    assert frame_idx > 0, "No frames captured"
    
    if latencies_ms:
        avg_latency = mean(latencies_ms)
        min_latency = min(latencies_ms)
        max_latency = max(latencies_ms)
        
        # Reasonable inference latency bounds for embedded device
        assert avg_latency < 5000.0, f"Average latency too high: {avg_latency:.2f}ms"
        assert max_latency < 10000.0, f"Max latency too high: {max_latency:.2f}ms"
        
        print(f"\n[HIL][SUMMARY] Processed {frame_idx} frames, {person_frames} with detections")
        print(f"  Inference latency (ms): avg={avg_latency:.2f}, min={min_latency:.2f}, max={max_latency:.2f}")
