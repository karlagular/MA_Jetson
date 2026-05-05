#!/usr/bin/env python3
"""One-shot Bambu Lab X1E stop test over LAN (MQTT)."""

import json
import os
import ssl
import sys
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "machine_config.json")
)


ACTIVE_STATES = {"RUNNING", "PAUSE", "PAUSED", "PAUSING", "RESUMING", "PREPARE"}


def _load_bambu_cfg() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"machine_config.json not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "Bambulab" not in cfg:
        raise KeyError("No 'Bambulab' section in machine_config.json")

    bambu = cfg["Bambulab"]
    required = ["host", "access_code", "serial"]
    missing = [k for k in required if not bambu.get(k) or str(bambu.get(k)).startswith("YOUR_")]
    if missing:
        raise ValueError(f"Bambulab config is missing required fields: {', '.join(missing)}")

    host = str(bambu["host"]).strip()
    if host == "0.0.0.0":
        raise ValueError(
            "Bambulab host is set to 0.0.0.0 in machine_config.json; set it to the printer LAN IP"
        )

    return bambu


def _find_first_key(node: Any, target_keys: set[str]) -> str | None:
    """Recursively find first string value for any key in target_keys."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in target_keys and isinstance(v, str):
                return v
            found = _find_first_key(v, target_keys)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_first_key(item, target_keys)
            if found:
                return found
    return None


def _is_active_state(state: str | None) -> bool:
    if not state:
        return False
    return state.strip().upper() in ACTIVE_STATES


def _new_sequence_id() -> str:
    return str(time.time_ns())


def main() -> int:
    try:
        cfg = _load_bambu_cfg()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    host = cfg["host"]
    serial = cfg["serial"]
    access_code = cfg["access_code"]

    request_topic = f"device/{serial}/request"
    report_topic = f"device/{serial}/report"

    latest_state = {"value": None}
    latest_payload = {"value": None}
    latest_print_result = {"value": None}
    latest_print_reason = {"value": None}
    report_event = threading.Event()

    def on_connect(client, _userdata, _flags, reason_code, _properties=None):
        if reason_code != 0:
            print(f"[ERROR] MQTT connect failed with reason_code={reason_code}")
            return
        client.subscribe(report_topic)

    def on_message(_client, _userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return

        latest_payload["value"] = payload
        state = _find_first_key(payload, {"gcode_state", "print_state", "state"})
        if state:
            latest_state["value"] = state

        if isinstance(payload, dict) and isinstance(payload.get("print"), dict):
            p = payload["print"]
            if isinstance(p.get("result"), str):
                latest_print_result["value"] = p.get("result")
            if isinstance(p.get("reason"), str):
                latest_print_reason["value"] = p.get("reason")

        report_event.set()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set("bblp", access_code)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[INFO] Connecting to Bambu broker at {host}:8883")
    try:
        client.connect(host, 8883, keepalive=15)
    except Exception as exc:
        print(f"[ERROR] Failed to connect to MQTT broker: {exc}")
        return 1

    client.loop_start()

    try:
        # Ask the printer to push full status so we can establish baseline state.
        status_request = {
            "pushing": {
                "sequence_id": _new_sequence_id(),
                "command": "pushall",
            }
        }
        client.publish(request_topic, json.dumps(status_request))

        print("[INFO] Waiting for baseline status report...")
        report_event.wait(timeout=6.0)
        baseline_state = latest_state["value"]
        print(f"[INFO] Baseline state: {baseline_state!r}")

        if not _is_active_state(baseline_state):
            print("[OK] No active print job detected; printer already idle/finished.")
            return 0

        # Minimal schema matching what worked for pause.
        stop_request = {
            "print": {
                "sequence_id": _new_sequence_id(),
                "command": "stop",
            }
        }

        print(f"[INFO] Sending stop command on {request_topic}")
        print(f"[INFO] Payload: {json.dumps(stop_request)}")
        latest_print_result["value"] = None
        latest_print_reason["value"] = None
        client.publish(request_topic, json.dumps(stop_request))

        # Strong confirmation polling: wait for state to leave active print states.
        deadline = time.time() + 20.0
        while time.time() < deadline:
            if not _is_active_state(latest_state["value"]):
                print(f"[OK] Stop confirmed by report state: {latest_state['value']!r}")
                return 0

            result = (latest_print_result["value"] or "").strip().upper()
            reason = (latest_print_reason["value"] or "").strip()
            if result == "FAIL":
                print(f"[ERROR] Printer reported stop failure: reason={reason!r}")
                if "verify" in reason.lower():
                    print("[HINT] MQTT command verification failed on printer side.")
                break

            report_event.wait(timeout=0.5)
            report_event.clear()

        print(
            "[ERROR] Stop command sent but inactive state was not observed. "
            f"Last seen state: {latest_state['value']!r}"
        )
        if latest_payload["value"] is not None:
            print("[INFO] Last report payload snippet:")
            preview = json.dumps(latest_payload["value"], indent=2)
            print(preview[:1200])
        return 1
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
