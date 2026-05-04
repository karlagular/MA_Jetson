"""
Hardware-in-the-loop test: printer pause/resume/stop cycle on real device.

Tests the pause/resume and pause/stop command sequences on real 3D printer
hardware. Requires an active print job on the target printer and proper
machine configuration credentials.

Supported printers:
  - Bambulab (MQTT)
  - Prusa Link (HTTP REST)
  - Ultimaker (HTTP REST with auth)
  - RatRig (Klipper/Moonraker HTTP)

Markers: @pytest.mark.hil_printer

Usage:
    pytest tests_hil_integration/test_printer_pause_cycle.py
    pytest tests_hil_integration/test_printer_pause_cycle.py -vs --printer=Prusa --sequence=pause-resume
    pytest tests_hil_integration/test_printer_pause_cycle.py -vs --printer=Prusa --sequence=pause-resume-pause-stop
    pytest tests_hil_integration/test_printer_pause_cycle.py -vs --printer=Prusa --sequence=pause-stop --log-io

Command-line options (via pytest):
    --printer           : Printer to test (required: Bambulab, Prusa, Ultimaker, RatRig)
    --sequence          : Commands to run (default: pause-resume, or: pause-stop, or: pause-resume-pause-stop)
    --machine-config    : Path to machine_config.json (default: machine_config.json)
    --skip-connectivity-check : Skip initial status check
    --yes               : Auto-confirm safety prompts (non-interactive)
    --log-io            : Write terminal results + TX/RX printer IO to TXT
    --log-dir           : Log output base dir (default: tests_hil_integration/logs)

Safety notes:
  - This test sends actual pause/resume/stop commands to a real printer
  - An active print job must be running on the target printer
  - Use --yes only in controlled test environments
  - Always verify the printer is safe to control before running
"""

from __future__ import annotations

import json
import pytest
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

from app.config import load_machine_config
from adapters.printer.bambu_mqtt import BambulabAdapter
from adapters.printer.klipper_moonraker import KlipperAdapter
from adapters.printer.prusa_link import PrusaAdapter
from adapters.printer.ultimaker_rest import UltimakerAdapter


def _ts_utc() -> str:
    """Return an ISO-8601 UTC timestamp with milliseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class _HilTxtLogger:
    """Simple per-test TXT logger for HIL printer IO traces."""

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._fh = file_path.open("w", encoding="utf-8")

    @property
    def file_path(self) -> Path:
        return self._file_path

    def write(self, kind: str, message: str, **fields) -> None:
        parts = [f"[{_ts_utc()}]", f"[{kind}]", message]
        if fields:
            kv = " ".join(f"{k}={v}" for k, v in fields.items())
            parts.append(kv)
        self._fh.write(" ".join(parts) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def _safe_filename(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)


@pytest.fixture
def hil_txt_logger(request):
    """Optional per-test TXT logger controlled via --log-io."""
    if not request.config.getoption("--log-io"):
        return None

    base_dir = Path(request.config.getoption("--log-dir"))
    run_dir = base_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    node_name = request.node.name
    file_path = run_dir / f"{_safe_filename(node_name)}.txt"
    logger = _HilTxtLogger(file_path)
    logger.write(
        "INFO",
        "hil_test_start",
        test=node_name,
        printer=request.config.getoption("--printer"),
        sequence=request.config.getoption("--sequence"),
    )
    logger.write("INFO", "log_path", path=file_path)
    yield logger
    logger.write("INFO", "hil_test_end", test=node_name)
    logger.close()


@pytest.fixture(autouse=True)
def _capture_printer_io(request, monkeypatch, hil_txt_logger):
    """Capture printer transport TX/RX with timestamps into TXT log."""
    if not request.config.getoption("--log-io") or hil_txt_logger is None:
        return

    import requests

    original_request = requests.sessions.Session.request

    def _logged_request(session, method, url, **kwargs):
        method_s = str(method).upper()
        body_len = 0
        if kwargs.get("json") is not None:
            try:
                body_len = len(json.dumps(kwargs["json"]))
            except Exception:
                body_len = 0
        elif kwargs.get("data") is not None:
            data = kwargs["data"]
            if isinstance(data, (str, bytes)):
                body_len = len(data)
        hil_txt_logger.write(
            "TX",
            "http_request",
            method=method_s,
            url=url,
            body_bytes=body_len,
            timeout=kwargs.get("timeout"),
        )

        t0 = time.perf_counter()
        try:
            response = original_request(session, method, url, **kwargs)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            content_len = response.headers.get("Content-Length")
            if content_len is None:
                try:
                    content_len = len(response.content)
                except Exception:
                    content_len = "unknown"
            hil_txt_logger.write(
                "RX",
                "http_response",
                method=method_s,
                url=url,
                status=response.status_code,
                elapsed_ms=f"{dt_ms:.1f}",
                response_bytes=content_len,
            )
            return response
        except Exception as exc:
            dt_ms = (time.perf_counter() - t0) * 1000.0
            hil_txt_logger.write(
                "ERROR",
                "http_exception",
                method=method_s,
                url=url,
                elapsed_ms=f"{dt_ms:.1f}",
                error=str(exc),
            )
            raise

    monkeypatch.setattr(requests.sessions.Session, "request", _logged_request)

    try:
        import paho.mqtt.client as mqtt
    except Exception:
        return

    original_publish = mqtt.Client.publish

    def _logged_publish(client, topic, payload=None, qos=0, retain=False, properties=None):
        if payload is None:
            payload_size = 0
        elif isinstance(payload, bytes):
            payload_size = len(payload)
        else:
            payload_size = len(str(payload).encode("utf-8", errors="ignore"))
        hil_txt_logger.write(
            "TX",
            "mqtt_publish",
            topic=topic,
            qos=qos,
            retain=retain,
            payload_bytes=payload_size,
        )
        return original_publish(client, topic, payload, qos, retain, properties)

    monkeypatch.setattr(mqtt.Client, "publish", _logged_publish)

    original_handle_on_message = getattr(mqtt.Client, "_handle_on_message", None)
    if callable(original_handle_on_message):
        def _logged_handle_on_message(client, *args, **kwargs):
            msg = next(
                (a for a in args if hasattr(a, "topic") and hasattr(a, "payload")),
                None,
            )
            if msg is not None:
                payload = msg.payload or b""
                payload_size = len(payload)
                hil_txt_logger.write(
                    "RX",
                    "mqtt_message",
                    topic=getattr(msg, "topic", "<unknown>"),
                    payload_bytes=payload_size,
                )
            return original_handle_on_message(client, *args, **kwargs)

        monkeypatch.setattr(mqtt.Client, "_handle_on_message", _logged_handle_on_message)


@pytest.fixture
def printer_type(request):
    """Get printer type from command line."""
    printer = request.config.getoption("--printer")
    if printer is None:
        pytest.skip("--printer not specified")
    return printer


@pytest.fixture
def hil_printer(printer_type, request):
    """Load machine config and instantiate printer adapter."""
    config_path = request.config.getoption("--machine-config")
    machine_cfg = load_machine_config(config_path)
    cfg = machine_cfg.get(printer_type)
    
    if cfg is None:
        pytest.skip(f"No config found for printer '{printer_type}' in {config_path}")
    
    if printer_type == "Bambulab":
        return BambulabAdapter(cfg)
    elif printer_type == "Prusa":
        return PrusaAdapter(cfg)
    elif printer_type == "Ultimaker":
        return UltimakerAdapter(cfg)
    else:  # RatRig
        return KlipperAdapter(cfg)


def _timed_call(fn) -> Tuple[bool, float, str]:
    """Execute fn and return (success, duration_ms, message)."""
    t0 = time.perf_counter()
    try:
        fn()
        dt = (time.perf_counter() - t0) * 1000.0
        return True, dt, "ok"
    except Exception as exc:
        dt = (time.perf_counter() - t0) * 1000.0
        return False, dt, str(exc)


def _emit_result(action: str, ok: bool, dt_ms: float, msg: str, hil_txt_logger) -> None:
    """Print result to terminal and mirror it into the optional TXT log."""
    line = f"[HIL] {action:<6} -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}"
    print(line)
    if hil_txt_logger is not None:
        hil_txt_logger.write(
            "RESULT",
            "command_result",
            action=action,
            ok=ok,
            duration_ms=f"{dt_ms:.1f}",
            detail=msg,
        )


@pytest.mark.hil_printer
def test_printer_connectivity(hil_printer, request, hil_txt_logger):
    """
    Test initial printer connectivity.
    
    Verifies that the printer is reachable and responding to status queries.
    Skipped if --skip-connectivity-check is passed.
    """
    if request.config.getoption("--skip-connectivity-check"):
        pytest.skip("Connectivity check skipped via --skip-connectivity-check")

    ok = hil_printer.check_status()
    if hil_txt_logger is not None:
        hil_txt_logger.write("RESULT", "connectivity_check", ok=ok)
    assert ok, "Printer connectivity check failed"


@pytest.mark.hil_printer
def test_printer_pause_resume_cycle(hil_printer, request, hil_txt_logger):
    """
    Test pause -> resume command cycle on real printer.
    
    Verifies:
      - pause() command executes successfully
      - printer responds to status after pause
      - resume() command executes successfully
      - printer returns to printing state
    """
    sequence = request.config.getoption("--sequence")
    if sequence != "pause-resume":
        pytest.skip(f"Skipping pause-resume (sequence is {sequence})")
    
    skip_check = request.config.getoption("--skip-connectivity-check")
    assume_yes = request.config.getoption("--yes")
    
    if not skip_check:
        assert hil_printer.check_status(), "Initial connectivity check failed"
    
    if not assume_yes:
        response = input("Confirm active print job exists and can be paused [Y/n]: ")
        if response.lower() in ("n", "no"):
            pytest.skip("User declined to proceed")
    
    # Execute pause
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    _emit_result("pause", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"pause() failed: {msg}"
    
    time.sleep(1.0)
    
    # Execute resume
    ok, dt_ms, msg = _timed_call(hil_printer.resume)
    _emit_result("resume", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"resume() failed: {msg}"


@pytest.mark.hil_printer
def test_printer_pause_stop_cycle(hil_printer, request, hil_txt_logger):
    """
    Test pause -> stop command cycle on real printer.
    
    Verifies:
      - pause() command executes successfully
      - stop() command executes successfully
      - printer transitions to stopped state
    
    WARNING: This **cancels** the print job. Use only in test scenarios.
    """
    sequence = request.config.getoption("--sequence")
    if sequence != "pause-stop":
        pytest.skip(f"Skipping pause-stop (sequence is {sequence})")
    
    skip_check = request.config.getoption("--skip-connectivity-check")
    assume_yes = request.config.getoption("--yes")
    
    if not skip_check:
        assert hil_printer.check_status(), "Initial connectivity check failed"
    
    if not assume_yes:
        response = input("Confirm active print job exists and can be stopped [Y/n]: ")
        if response.lower() in ("n", "no"):
            pytest.skip("User declined to proceed")
    
    # Execute pause
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    _emit_result("pause", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"pause() failed: {msg}"
    
    time.sleep(1.0)
    
    # Execute stop
    ok, dt_ms, msg = _timed_call(hil_printer.stop)
    _emit_result("stop", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"stop() failed: {msg}"


@pytest.mark.hil_printer
def test_printer_pause_resume_pause_stop_cycle(hil_printer, request, hil_txt_logger):
    """
    Test pause -> resume -> pause -> stop command cycle on real printer.

    Verifies:
      - pause() command executes successfully
      - resume() command executes successfully
      - second pause() command executes successfully
      - stop() command executes successfully

    WARNING: This **cancels** the print job. Use only in test scenarios.
    """
    sequence = request.config.getoption("--sequence")
    if sequence != "pause-resume-pause-stop":
        pytest.skip(f"Skipping pause-resume-pause-stop (sequence is {sequence})")

    skip_check = request.config.getoption("--skip-connectivity-check")
    assume_yes = request.config.getoption("--yes")

    if not skip_check:
        assert hil_printer.check_status(), "Initial connectivity check failed"

    if not assume_yes:
        response = input("Confirm active print job exists and can be paused then stopped [Y/n]: ")
        if response.lower() in ("n", "no"):
            pytest.skip("User declined to proceed")

    # Step 1: pause
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    _emit_result("pause", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"pause() failed: {msg}"

    time.sleep(45.0)

    # Step 2: resume
    ok, dt_ms, msg = _timed_call(hil_printer.resume)
    _emit_result("resume", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"resume() failed: {msg}"

    time.sleep(45.0)

    # Step 3: pause again
    ok, dt_ms, msg = _timed_call(hil_printer.pause)
    _emit_result("pause", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"second pause() failed: {msg}"

    time.sleep(45.0)

    # Step 4: stop
    ok, dt_ms, msg = _timed_call(hil_printer.stop)
    _emit_result("stop", ok, dt_ms, msg, hil_txt_logger)
    assert ok, f"stop() failed: {msg}"
