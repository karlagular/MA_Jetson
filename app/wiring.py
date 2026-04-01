"""Composition Root — build the full dependency graph from config."""

from __future__ import annotations

from app.config import ExperimentConfig, load_machine_config
from domain.policy import MofNPolicy
from domain.state_machine import AlarmStateMachine
from domain.use_cases import AlarmOrchestrator
from pipeline.latency import LatencyTracker
from pipeline.processor import PipelineRunner
from ports.alarm_light import AlarmLightPort
from ports.camera import CameraPort
from ports.clock import ClockPort
from ports.inference import InferencePort
from ports.logger import EventLoggerPort
from ports.printer import PrinterPort
from ports.ui import UiPort


# ------------------------------------------------------------------
# Clock adapter (no separate file needed; tiny implementation)
# ------------------------------------------------------------------
import time as _time
from datetime import datetime as _datetime


class _SystemClock(ClockPort):
    def perf_counter(self) -> float:
        return _time.perf_counter()

    def now(self) -> _datetime:
        return _datetime.now()


# ------------------------------------------------------------------
# Factory helpers
# ------------------------------------------------------------------

def _make_camera(cfg: ExperimentConfig) -> CameraPort:
    kamera = cfg.kamera
    if kamera == "USB Basler BW Fix":
        from adapters.camera.basler_pypylon import BaslerPylonCamera
        return BaslerPylonCamera()
    elif kamera == "RTSP rpi cam 3 wide":
        from adapters.camera.rtsp_gstreamer import RTSPGStreamerCamera
        rtsp_url = cfg.rtsp_url
        pipeline = (
            f"rtspsrc location={rtsp_url} latency=200 ! "
            "rtph264depay ! h264parse ! nvv4l2decoder ! "
            "nvvidconv ! video/x-raw,format=BGRx ! "
            "videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
        )
        return RTSPGStreamerCamera(pipeline)
    else:
        from adapters.camera.opencv_usb import OpenCVUSBCamera
        return OpenCVUSBCamera(device_id=0)


def _make_printer(machine_name: str, machine_configs: dict) -> PrinterPort:
    key = machine_name.lower()
    if key == "fake printer":
        from adapters.printer.fake_printer import FakePrinter
        return FakePrinter()

    cfg = machine_configs.get(machine_name)
    if cfg is None:
        raise ValueError(f"No config for printer '{machine_name}' in machine_config.json")

    if key == "ratrig":
        from adapters.printer.klipper_moonraker import KlipperAdapter
        return KlipperAdapter(cfg)
    elif key == "bambulab":
        from adapters.printer.bambu_mqtt import BambulabAdapter
        return BambulabAdapter(cfg)
    elif key == "prusa":
        from adapters.printer.prusa_link import PrusaAdapter
        return PrusaAdapter(cfg)
    elif key == "ultimaker":
        from adapters.printer.ultimaker_rest import UltimakerAdapter
        return UltimakerAdapter(cfg)
    else:
        raise ValueError(f"Unknown printer type: {machine_name}")


# ------------------------------------------------------------------
# Main wiring function
# ------------------------------------------------------------------

def wire(cfg: ExperimentConfig, session_id: str) -> tuple:
    """Build all objects and return (pipeline, ui_window, camera).

    Returns the UI window separately so the caller can ``show()`` it
    before starting the QTimer.
    """
    import os
    from adapters.alarm_light.dummy_light import DummyLight
    from adapters.inference.ultralytics_yolo import UltralyticsYOLO
    from adapters.logging.jsonl_logger import JsonlLogger
    from adapters.ui.qt_app import QtVideoWindow

    clock = _SystemClock()
    machine_configs = load_machine_config()

    # Ports / adapters
    camera = _make_camera(cfg)
    inference = UltralyticsYOLO(cfg.model_path, conf=0.5)
    printer = _make_printer(cfg.maschine, machine_configs)
    alarm_light: AlarmLightPort = DummyLight()
    session_dir = os.path.join("experimental_results", session_id)
    logger: EventLoggerPort = JsonlLogger(session_dir)

    # Domain
    policy = MofNPolicy(m=cfg.alarm_m, n=cfg.alarm_n)
    sm = AlarmStateMachine()

    # UI (must be created in Qt thread — fine, wire() is always called from main)
    ui = QtVideoWindow(on_model_change=None)  # will be patched below

    orchestrator = AlarmOrchestrator(
        policy=policy,
        state_machine=sm,
        printer=printer,
        alarm_light=alarm_light,
        ui=ui,
        logger=logger,
        clock=clock,
    )

    latency = LatencyTracker(clock=clock, window_size=60, session_id=session_id)

    pipeline = PipelineRunner(
        camera=camera,
        inference=inference,
        ui=ui,
        orchestrator=orchestrator,
        latency_tracker=latency,
        clock=clock,
    )

    # Now patch model-change callback through to the pipeline
    ui._on_model_change = pipeline.change_model

    # Check printer connectivity
    try:
        if printer.check_status():
            print(f"[Config] Printer '{cfg.maschine}' is connected and available")
        else:
            print(f"[Config] WARNING: Printer '{cfg.maschine}' is not connected or not reachable")
    except Exception as exc:
        print(f"[Config] WARNING: Printer '{cfg.maschine}' check failed: {exc}")

    return pipeline, ui, camera
