#!/usr/bin/env python3
"""Tiny Bambu Lab pause-command schema probe over LAN MQTT."""

import json
import os
import ssl
import sys
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "machine_config.json")


def _load_bambu_cfg() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    bambu = cfg.get("Bambulab", {})
    required = ["host", "access_code", "serial"]
    missing = [k for k in required if not bambu.get(k) or str(bambu.get(k)).startswith("YOUR_")]
    if missing:
        raise ValueError(f"Bambulab config missing: {', '.join(missing)}")
    return bambu


def _find_first_key(node: Any, keys: set[str]) -> str | None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in keys and isinstance(v, str):
                return v
            found = _find_first_key(v, keys)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_first_key(item, keys)
            if found:
                return found
    return None


def _extract_text(node: Any) -> str:
    try:
        return json.dumps(node).lower()
    except Exception:
        return str(node).lower()


def _new_seq() -> str:
    return str(time.time_ns())


def _reason_code_is_success(reason_code: Any) -> bool:
    """Handle Paho reason code compatibility across versions."""
    if reason_code is None:
        return False

    # v1-style numeric rc
    if isinstance(reason_code, (int, float)):
        return int(reason_code) == 0

    # v2 ReasonCode object often exposes value or compares to 0
    value = getattr(reason_code, "value", None)
    if isinstance(value, (int, float)):
        return int(value) == 0

    text = str(reason_code).strip().lower()
    return text in {"0", "success"}


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

    def on_connect(client, _userdata, _flags, reason_code, _properties):
        if not _reason_code_is_success(reason_code):
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

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set("bblp", access_code)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[INFO] Connecting to {host}:8883")
    client.connect(host, 8883, keepalive=15)
    client.loop_start()

    try:
        # Ask for baseline report first.
        client.publish(
            request_topic,
            json.dumps({"pushing": {"sequence_id": _new_seq(), "command": "pushall"}}),
        )
        report_event.wait(timeout=4.0)
        baseline_state = latest_state["value"]
        print(f"[INFO] Baseline state: {baseline_state!r}")

        candidates = [
            ("pause_minimal", lambda: {"print": {"sequence_id": _new_seq(), "command": "pause"}}),
            (
                "pause_with_param",
                lambda: {"print": {"sequence_id": _new_seq(), "command": "pause", "param": ""}},
            ),
            (
                "pause_seq_int_like",
                lambda: {"print": {"sequence_id": str(int(time.time())), "command": "pause"}},
            ),
        ]

        user_id = None
        if isinstance(latest_payload["value"], dict):
            user_id = _find_first_key(latest_payload["value"], {"user_id"})
        if user_id:
            candidates.append(
                (
                    "pause_with_user_id",
                    lambda: {
                        "print": {
                            "sequence_id": _new_seq(),
                            "command": "pause",
                            "param": "",
                            "user_id": user_id,
                        }
                    },
                )
            )

        accepted = []
        for name, payload_builder in candidates:
            report_event.clear()
            before_state = latest_state["value"]
            payload = payload_builder()
            print(f"\n[TEST] {name}")
            print(f"[SEND] {json.dumps(payload)}")
            client.publish(request_topic, json.dumps(payload))

            got_report = report_event.wait(timeout=3.0)
            after_state = latest_state["value"]
            text = _extract_text(latest_payload["value"]) if latest_payload["value"] else ""

            looks_rejected = (
                ("verify" in text and "fail" in text)
                or "authorization required" in text
                or "error" in text
            )
            state_changed_to_pause = after_state and after_state.upper() in {"PAUSE", "PAUSED", "PAUSING"}

            if state_changed_to_pause:
                print(f"[RESULT] ACCEPTED (state -> {after_state!r})")
                accepted.append(name)
            elif got_report and not looks_rejected:
                print(f"[RESULT] POSSIBLY ACCEPTED (report received, state {before_state!r} -> {after_state!r})")
            else:
                print(f"[RESULT] REJECTED/UNKNOWN (state {before_state!r} -> {after_state!r})")
                if latest_payload["value"] is not None:
                    snippet = json.dumps(latest_payload["value"], indent=2)
                    print("[DETAIL] Last report snippet:")
                    print(snippet[:800])

        print("\n[SUMMARY]")
        if accepted:
            print(f"Accepted schema(s): {', '.join(accepted)}")
            return 0

        print("No payload form was clearly accepted.")
        return 1
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
