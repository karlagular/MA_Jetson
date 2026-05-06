"""
Interactive system test: real camera + real inference + Qt UI + fake printer.

What this test does:
  - Opens the Qt stream window and displays the processed video stream.
  - Shows alarm dialogs when defects trigger the alarm policy.
  - Always auto-selects "Continue printing" 1 second after alarm buttons enable.
  - Runs until the operator manually stops it via terminal input.
  - Logs alarm events and alarm snapshot frames with JsonlLogger.

Usage:
  pytest -s System_Test/test_alarm_count_fake_printer.py::test_alarm_count_with_fake_printer

Optional camera/model arguments:
  --system-camera basler|usb|replay
  --system-basler-serial SERIAL
  --system-usb-device 0
  --system-usb-width 640
  --system-usb-height 480
  --system-video-path /path/to/video.mp4
    --system-model-path models_available/best.pt
  --system-conf 0.5
    --m <int> --n <int> --d <int>

Log output:
  System_Test/logs/<timestamp>/events.jsonl
  System_Test/logs/<timestamp>/defect_alarm_*.jpg
    System_Test/logs/<timestamp>/latency_log.txt
  System_Test/logs/<timestamp>/summary.json
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import pytest
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.alarm_light.dummy_light import DummyLight
from adapters.camera.basler_pypylon import BaslerPylonCamera
from adapters.camera.opencv_usb import OpenCVUSBCamera
from adapters.camera.replay_video import ReplayVideoCamera
from adapters.inference.ultralytics_yolo import UltralyticsYOLO
from adapters.logging.jetson_system_metrics_logger import JetsonSystemMetricsLogger
from adapters.logging.jsonl_logger import JsonlLogger
from adapters.printer.fake_printer import FakePrinter
from adapters.ui.qt_app import QtVideoWindow
from app.alarm_runtime import AlarmRuntime
from app.orchestrator import AlarmOrchestrator
from domain.models import FramePacket
from domain.policy import MofNPolicy
from domain.state_machine import AlarmStateMachine
from pipeline.steps import draw_overlay
from ports.clock import ClockPort
from ports.ui import UiPort


class _SystemClock(ClockPort):
    def perf_counter(self) -> float:
        return time.perf_counter()

    def now(self) -> datetime:
        return datetime.now()


class AutoContinueQtUi(UiPort):
    """UiPort wrapper that uses QtVideoWindow and auto-continues alarms."""

    def __init__(self, continue_delay_s: float) -> None:
        self._window = QtVideoWindow()
        self._continue_delay_ms = max(0, int(continue_delay_s * 1000.0))
        self._on_continue: Callable[[], None] | None = None
        self._on_stop: Callable[[], None] | None = None
        self._alarm_open = False
        self._auto_continue_scheduled = False
        self.alarm_count = 0

    @property
    def window(self) -> QtVideoWindow:
        return self._window

    def display_frame(self, frame) -> None:
        self._window.display_frame(frame)

    def show_alarm(self, on_continue: Callable[[], None], on_stop: Callable[[], None]) -> None:
        self._on_continue = on_continue
        self._on_stop = on_stop
        self._alarm_open = True
        self._auto_continue_scheduled = False
        self.alarm_count += 1
        self._window.show_alarm(on_continue=on_continue, on_stop=on_stop)

    def dismiss_alarm(self) -> None:
        self._alarm_open = False
        self._auto_continue_scheduled = False
        self._window.dismiss_alarm()

    def enable_alarm_buttons(self) -> None:
        self._window.enable_alarm_buttons()
        if self._alarm_open and not self._auto_continue_scheduled:
            self._auto_continue_scheduled = True
            QTimer.singleShot(self._continue_delay_ms, self._trigger_continue)

    def request_application_shutdown(self) -> None:
        self._window.request_application_shutdown()

    def _trigger_continue(self) -> None:
        if not self._alarm_open:
            return
        if self._on_continue is not None:
            self._on_continue()
        self.dismiss_alarm()


def _make_camera(request):
    camera_type = request.config.getoption("--system-camera")
    if camera_type == "basler":
        return BaslerPylonCamera(serial=request.config.getoption("--system-basler-serial"))
    if camera_type == "usb":
        return OpenCVUSBCamera(
            device_id=request.config.getoption("--system-usb-device"),
            width=request.config.getoption("--system-usb-width"),
            height=request.config.getoption("--system-usb-height"),
        )

    video_path = request.config.getoption("--system-video-path")
    if not video_path:
        pytest.fail("--system-video-path is required when --system-camera=replay")
    return ReplayVideoCamera(video_path=video_path, loop=True)


def _start_manual_stop_thread(stop_event: threading.Event) -> threading.Thread:
    def _wait_for_enter() -> None:
        print("[SystemTest] Press ENTER in this terminal to stop the test.")
        try:
            input()
        except EOFError:
            # Non-interactive stdin: keep running until external interruption.
            return
        stop_event.set()

    thread = threading.Thread(target=_wait_for_enter, daemon=True)
    thread.start()
    return thread


def _render_mask_frame(result, frame_shape: tuple[int, ...]) -> np.ndarray | None:
    if not result.masks:
        return None

    h, w = frame_shape[:2]
    merged = np.zeros((h, w), dtype=np.uint8)
    for mask in result.masks:
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        merged[mask.astype(bool)] = 255
    return np.stack([merged, merged, merged], axis=-1)


def test_alarm_count_with_fake_printer(request):
    """Interactive system test that counts alarm activations with fake printer."""
    if not sys.stdin or not sys.stdin.isatty():
        pytest.skip("Interactive terminal required. Run with: pytest -s ...")

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_log_dir = Path(request.config.getoption("--system-log-dir"))
    run_dir = base_log_dir / run_stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    logger = JsonlLogger(
        str(run_dir),
        alarm_m=request.config.getoption("--system-alarm-m"),
        alarm_n=request.config.getoption("--system-alarm-n"),
        alarm_disappear_frames=request.config.getoption("--system-alarm-disappear-frames"),
        inference_conf=request.config.getoption("--system-conf"),
    )
    system_metrics_logger = JetsonSystemMetricsLogger(str(run_dir), interval_seconds=2.0)
    camera = _make_camera(request)
    inference = UltralyticsYOLO(
        model_path=request.config.getoption("--system-model-path"),
        conf=request.config.getoption("--system-conf"),
        safe_class_id=request.config.getoption("--system-safe-class-id"),
    )
    printer = FakePrinter()
    qt_app = QApplication.instance() or QApplication([])
    ui = AutoContinueQtUi(continue_delay_s=request.config.getoption("--system-continue-delay-s"))
    clock = _SystemClock()

    policy = MofNPolicy(
        m=request.config.getoption("--system-alarm-m"),
        n=request.config.getoption("--system-alarm-n"),
        disappear_frames=request.config.getoption("--system-alarm-disappear-frames"),
    )
    sm = AlarmStateMachine()
    orchestrator = AlarmOrchestrator(policy=policy, state_machine=sm, clock=clock)
    runtime = AlarmRuntime(
        orchestrator=orchestrator,
        printer=printer,
        alarm_light=DummyLight(),
        ui=ui,
        logger=logger,
    )

    ui.window.show()

    camera_type = request.config.getoption("--system-camera")
    try:
        opened = camera.open()
    except Exception as exc:
        msg = str(exc)
        if camera_type == "basler" and "exclusively opened" in msg.lower():
            pytest.skip(
                "Basler camera is locked by another process. "
                "Close other camera clients (for example pylon viewer, app.main, or another test) and retry."
            )
        pytest.fail(f"Camera open raised an exception: {exc}")

    if not opened:
        if camera_type == "basler":
            pytest.skip(
                "Basler camera could not be opened. Ensure no other process is using it, then rerun the test."
            )
        pytest.fail("Camera open failed")

    stop_event = threading.Event()
    _start_manual_stop_thread(stop_event)

    frame_count = 0
    latency_records: list[tuple] = []
    colors = [[0, 255, 0], [0, 180, 255], [255, 200, 0], [255, 0, 0]]
    alarm_m = request.config.getoption("--system-alarm-m")
    alarm_n = request.config.getoption("--system-alarm-n")
    alarm_d = request.config.getoption("--system-alarm-disappear-frames")
    conf = request.config.getoption("--system-conf")

    print(f"[SystemTest] Logging run to: {run_dir}")
    print(f"[SystemTest] System metrics log: {run_dir / 'system_metrics.jsonl'}")
    print(f"[SystemTest] Active alarm policy: M={alarm_m} N={alarm_n} D={alarm_d} Conf={conf:.2f}")
    print("[SystemTest] Running... alarms will auto-continue after 1 second.")

    system_metrics_logger.start()
    try:
        while not stop_event.is_set():
            t0 = clock.perf_counter()
            ok, frame = camera.read_frame()
            t1 = clock.perf_counter()
            if not ok or frame is None:
                break

            result = inference.predict(frame)
            t2 = clock.perf_counter()
            overlay = draw_overlay(frame, result, colors)
            mask_frame = _render_mask_frame(result, frame.shape)
            t3 = clock.perf_counter()

            packet_ts = int(clock.perf_counter() * 1e9)
            runtime.handle_detection(
                result=result,
                packet=FramePacket(
                    frame=overlay,
                    index=frame_count,
                    timestamp_ns=packet_ts,
                    raw_frame=frame.copy(),
                    mask_frame=mask_frame,
                ),
            )
            runtime.process_pending_events()
            t4 = clock.perf_counter()

            ui.display_frame(overlay)
            qt_app.processEvents()
            t5 = clock.perf_counter()

            latency_records.append(
                (
                    frame_count,
                    (t1 - t0) * 1000.0,
                    (t2 - t1) * 1000.0,
                    (t3 - t2) * 1000.0,
                    (t4 - t3) * 1000.0,
                    (t5 - t4) * 1000.0,
                    (t5 - t0) * 1000.0,
                )
            )

            frame_count += 1
            if frame_count % 120 == 0:
                print(f"[SystemTest] frames={frame_count} alarms={ui.alarm_count}")

            # Keeps the UI responsive without busy-waiting.
            time.sleep(0.001)
    finally:
        system_metrics_logger.stop()
        logger.save_latency_log(latency_records)
        runtime.shutdown(frame_count=frame_count)
        camera.close()
        qt_app.processEvents()
        ui.window.close()

    print("\n[SystemTest][SUMMARY]")
    print(f"  frames processed : {frame_count}")
    print(f"  alarms activated : {ui.alarm_count}")
    print(f"  fake printer calls: {printer.calls}")
    print(f"  summary          : {run_dir / 'summary.json'}")

    assert frame_count > 0, "No frames were processed"
