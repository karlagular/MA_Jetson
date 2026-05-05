#!/usr/bin/env python3
"""One-time Ultimaker pairing helper.

This script performs Ultimaker API pairing and stores credentials in
machine_config.json so they can be reused from the Jetson indefinitely.
"""

import json
import os
import socket
import sys
import time
from datetime import datetime

import requests

PRINTER_IP = "169.254.221.192"
CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "machine_config.json")
)


def _load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _parse_pairing_data(payload: dict) -> tuple[str | None, str | None]:
    """Extract pairing id and key from different Ultimaker firmware variants."""
    pair_id = payload.get("id") or payload.get("auth_id") or payload.get("request_id")
    pair_key = payload.get("key") or payload.get("auth_key") or payload.get("password")
    return pair_id, pair_key


def main() -> int:
    base_url = f"http://{PRINTER_IP}"
    request_url = f"{base_url}/api/v1/auth/request"

    host_name = socket.gethostname()
    app_name = "synthforge-jetson"
    user_name = host_name

    request_payload = {
        "application": app_name,
        "user": user_name,
        "host_name": host_name,
    }

    print(f"[INFO] Sending pairing request to {request_url}")
    try:
        response = requests.post(request_url, json=request_payload, timeout=10)
    except requests.exceptions.RequestException as exc:
        print(f"[ERROR] Pairing request failed: {exc}")
        return 1

    if not (200 <= response.status_code < 300):
        print(f"[ERROR] Pairing request rejected: HTTP {response.status_code}")
        print(response.text.strip() or "<empty>")
        return 1

    try:
        response_payload = response.json()
    except json.JSONDecodeError:
        print("[ERROR] Pairing request returned non-JSON payload.")
        print(response.text.strip() or "<empty>")
        return 1

    pair_id, pair_key = _parse_pairing_data(response_payload)
    if not pair_id or not pair_key:
        print("[ERROR] Could not parse pairing id/key from printer response.")
        print(json.dumps(response_payload, indent=2))
        return 1

    print("[ACTION] Approve the pairing request on the Ultimaker touchscreen now.")

    check_url = f"{base_url}/api/v1/auth/check/{pair_id}"
    timeout_seconds = 120
    started = time.time()
    approved = False

    while (time.time() - started) < timeout_seconds:
        try:
            check_response = requests.get(check_url, timeout=10)
        except requests.exceptions.RequestException as exc:
            print(f"[WARN] Poll failed: {exc}")
            time.sleep(2)
            continue

        if 200 <= check_response.status_code < 300:
            try:
                check_payload = check_response.json()
            except json.JSONDecodeError:
                check_payload = {"raw": check_response.text}

            text = str(check_payload).lower()
            if (
                "authorized" in text
                or "approved" in text
                or "granted" in text
                or '"active": true' in text
                or '"status": "ok"' in text
            ):
                approved = True
                break

        time.sleep(2)

    if not approved:
        print("[ERROR] Pairing was not approved within timeout.")
        print("Try again and confirm on printer within 2 minutes.")
        return 1

    config = _load_config()
    config.setdefault("Ultimaker", {})
    config["Ultimaker"].update(
        {
            "host": PRINTER_IP,
            # Ultimaker Digest auth expects the pairing id as username.
            "username": pair_id,
            "password": pair_key,
            "paired_at": datetime.now().isoformat(timespec="seconds"),
            "pairing_id": pair_id,
            "application": app_name,
            "display_user": user_name,
        }
    )
    _save_config(config)

    print("[OK] Pairing approved and credentials saved to machine_config.json")
    print(f"[OK] Saved Ultimaker host={PRINTER_IP}, username={pair_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
