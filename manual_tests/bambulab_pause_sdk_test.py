#!/usr/bin/env python3
"""Pause Bambu Lab print via high-level bambulabs-api SDK."""

import json
import os
import sys
import time

from bambulabs_api import GcodeState, Printer

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
        raise ValueError(f"Bambulab config missing required fields: {', '.join(missing)}")

    return bambu


def _state_name(state: object) -> str:
    if hasattr(state, "value"):
        return str(getattr(state, "value"))
    return str(state)


def main() -> int:
    try:
        cfg = _load_bambu_cfg()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    printer = Printer(
        ip_address=cfg["host"],
        access_code=cfg["access_code"],
        serial=cfg["serial"],
    )

    try:
        print(f"[INFO] Connecting to Bambu printer {cfg['host']} via SDK (MQTT only)")
        # Avoid camera TLS noise; pause/status only need MQTT.
        printer.mqtt_start()
        time.sleep(2.0)  # allow MQTT status cache to warm up

        baseline_state = printer.get_state()
        print(f"[INFO] Baseline state: {_state_name(baseline_state)!r}")

        if baseline_state == GcodeState.PAUSE:
            print("[OK] Printer is already paused.")
            return 0

        print("[INFO] Sending pause via sdk: printer.pause_print()")
        published = printer.pause_print()
        print(f"[INFO] SDK publish result: {published}")

        dump_now = printer.mqtt_dump()
        dump_now_text = json.dumps(dump_now).lower()
        if "mqtt message verify failed" in dump_now_text:
            print("[ERROR] Firmware rejected command verification immediately.")
            print("[HINT] LAN command signing/verification is blocking pause commands.")
            return 1

        deadline = time.time() + 8.0
        while time.time() < deadline:
            current_state = printer.get_state()
            if current_state == GcodeState.PAUSE:
                print("[OK] Pause confirmed by printer state.")
                return 0
            time.sleep(0.25)

        final_state = printer.get_state()
        print(f"[ERROR] Pause not confirmed. Final state: {_state_name(final_state)!r}")

        dump = printer.mqtt_dump()
        dump_text = json.dumps(dump, indent=2)
        if "mqtt message verify failed" in dump_text.lower():
            print("[HINT] Firmware rejected command verification (mqtt message verify failed).")
            print("[HINT] Regenerate LAN access code, reboot printer, and ensure LAN-only mode is enabled.")

        print("[INFO] MQTT dump snippet:")
        print(dump_text[:1500])
        return 1
    except Exception as exc:
        print(f"[ERROR] SDK pause request failed: {exc}")
        return 1
    finally:
        try:
            printer.mqtt_stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
