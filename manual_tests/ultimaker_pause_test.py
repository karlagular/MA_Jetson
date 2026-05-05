#!/usr/bin/env python3
"""One-shot Ultimaker S5 pause test using stored credentials."""

import json
import os
import sys
import time

import requests
from requests.auth import HTTPDigestAuth

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "machine_config.json")
)


def _load_ultimaker_cfg() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"machine_config.json not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "Ultimaker" not in cfg:
        raise KeyError("No 'Ultimaker' section in machine_config.json")

    um = cfg["Ultimaker"]
    required = ["host", "username", "password"]
    missing = [k for k in required if not um.get(k) or str(um.get(k)).startswith("YOUR_")]
    if missing:
        raise ValueError(f"Ultimaker config is missing required fields: {', '.join(missing)}")
    return um


def main() -> int:
    try:
        cfg = _load_ultimaker_cfg()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        print("Run: python3 ultimaker_pair_once.py")
        return 1

    base_url = f"http://{cfg['host'].rstrip('/')}"
    auth_candidates = [(cfg["username"], cfg["password"], "username")]
    if cfg.get("pairing_id") and cfg["pairing_id"] != cfg["username"]:
        auth_candidates.append((cfg["pairing_id"], cfg["password"], "pairing_id"))

    # Endpoint checks provided by user.
    print(f"[INFO] Checking job endpoint: {base_url}/api/v1/print_job")
    r_job = requests.get(f"{base_url}/api/v1/print_job", timeout=10)
    print(f"[INFO] GET /api/v1/print_job -> HTTP {r_job.status_code}")

    print(f"[INFO] Checking state endpoint: {base_url}/api/v1/print_job/state")
    r_state = requests.get(f"{base_url}/api/v1/print_job/state", timeout=10)
    pre_state = r_state.text.strip().strip('"')
    print(f"[INFO] GET /api/v1/print_job/state -> HTTP {r_state.status_code}, state={pre_state!r}")

    pause_url = f"{base_url}/api/v1/print_job/state"
    payload = {"target": "pause"}
    print(f"[INFO] Sending pause command to {pause_url} with Digest auth")

    r_pause = None
    for username, password, source in auth_candidates:
        try:
            r_pause = requests.put(
                pause_url,
                json=payload,
                auth=HTTPDigestAuth(username, password),
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            print(f"[WARN] Pause request failed with {source}: {exc}")
            continue

        if r_pause.status_code != 403:
            if source != "username":
                print(f"[INFO] Digest auth succeeded using {source} credentials.")
            break

    if r_pause is None:
        print("[ERROR] Pause request could not be sent with available credentials.")
        return 1

    print(f"[INFO] PUT /api/v1/print_job/state -> HTTP {r_pause.status_code}")
    if not (200 <= r_pause.status_code < 300):
        body = r_pause.text.strip().replace("\n", " ")
        print(f"[WARN] Pause response body: {body[:400] if body else '<empty>'}")

    time.sleep(1.0)
    r_after = requests.get(f"{base_url}/api/v1/print_job/state", timeout=10)
    post_state = r_after.text.strip().strip('"')
    print(f"[INFO] After pause: GET /api/v1/print_job/state -> HTTP {r_after.status_code}, state={post_state!r}")

    if post_state.lower() in {"paused", "pausing"}:
        print("[OK] Ultimaker pause confirmed by state endpoint.")
        return 0

    if 200 <= r_pause.status_code < 300:
        print("[OK] Pause command accepted. State did not yet report paused.")
        return 0

    print("[ERROR] Pause command failed or could not be confirmed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
