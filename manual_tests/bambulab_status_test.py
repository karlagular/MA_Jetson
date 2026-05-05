#!/usr/bin/env python3
"""One-shot Bambu Lab status fetch over LAN (MQTT)."""

import json
import os
import ssl
import sys
import threading
from typing import Any

import paho.mqtt.client as mqtt

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "machine_config.json")
)


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

    report_event = threading.Event()
    latest_payload = {"value": None}
    latest_state = {"value": None}

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
        # Ask printer for a full status push and wait for one report message.
        status_request = {
            "pushing": {
                "sequence_id": "0",
                "command": "pushall",
            }
        }
        client.publish(request_topic, json.dumps(status_request))

        print("[INFO] Waiting for printer status report...")
        received = report_event.wait(timeout=6.0)
        if not received or latest_payload["value"] is None:
            print("[ERROR] No status report received from printer.")
            return 1

        print(f"[OK] Received status report. State: {latest_state['value']!r}")
        print(json.dumps(latest_payload["value"], indent=2)[:4000])
        return 0
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
