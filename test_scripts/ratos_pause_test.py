#!/usr/bin/env python3
"""One-shot Ratos (Klipper/Moonraker) pause test script."""

import json
import os
import sys
import time

import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "machine_config.json")


def _load_ratrig_cfg() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"machine_config.json not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "RatRig" not in cfg:
        raise KeyError("No 'RatRig' section in machine_config.json")

    return cfg["RatRig"]


def _moonraker_base_url(cfg: dict) -> str:
    base = cfg.get("moonraker_url") or cfg.get("url") or cfg.get("host")
    if not base:
        raise ValueError("RatRig config needs 'moonraker_url' (or 'url'/'host')")

    if not str(base).startswith(("http://", "https://")):
        base = "http://" + str(base)

    return str(base).rstrip("/")


def _get_print_state(base_url: str) -> str | None:
    """Return Klipper print state from Moonraker, e.g. printing/paused/standby."""
    url = f"{base_url}/printer/objects/query?print_stats"
    try:
        r = requests.get(url, timeout=10)
        if not (200 <= r.status_code < 300):
            return None
        payload = r.json()
        return (
            payload.get("result", {})
            .get("status", {})
            .get("print_stats", {})
            .get("state")
        )
    except Exception:
        return None


def _pause_via_print_pause(base_url: str) -> requests.Response:
    return requests.post(f"{base_url}/printer/print/pause", timeout=10)


def _pause_via_gcode_pause(base_url: str) -> requests.Response:
    return requests.post(
        f"{base_url}/printer/gcode/script",
        json={"script": "PAUSE"},
        timeout=10,
    )


def main() -> int:
    try:
        cfg = _load_ratrig_cfg()
        base_url = _moonraker_base_url(cfg)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    baseline_state = _get_print_state(base_url)
    print(f"[INFO] Baseline print state: {baseline_state!r}")

    if baseline_state == "paused":
        print("[OK] Print is already paused.")
        return 0

    candidates = [
        ("POST", f"{base_url}/printer/print/pause", _pause_via_print_pause),
        ("POST", f"{base_url}/printer/gcode/script (PAUSE)", _pause_via_gcode_pause),
    ]

    for method, endpoint_label, sender in candidates:
        try:
            response = sender(base_url)
        except requests.exceptions.RequestException as exc:
            print(f"[WARN] {method} {endpoint_label} failed: {exc}")
            continue

        if 200 <= response.status_code < 300:
            time.sleep(0.8)
            current_state = _get_print_state(base_url)
            if current_state == "paused":
                print(f"[OK] Pause confirmed via {method} {endpoint_label}")
                return 0

            print(
                f"[OK] Pause command accepted via {method} {endpoint_label} "
                f"(HTTP {response.status_code}), current_state={current_state!r}"
            )
            return 0

        body = response.text.strip().replace("\n", " ")
        print(
            f"[WARN] {method} {endpoint_label} returned HTTP {response.status_code}; "
            f"response: {body[:300] if body else '<empty>'}"
        )

    print("[ERROR] Could not pause Ratos print with tested Moonraker endpoints.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
