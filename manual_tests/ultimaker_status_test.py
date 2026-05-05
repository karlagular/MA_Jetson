#!/usr/bin/env python3
"""One-shot Ultimaker S5 status test using stored credentials."""

import json
import os
import sys

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


def _request_with_auth_fallback(url: str, auth_candidates: list[tuple[str, str, str]]) -> tuple[requests.Response | None, str | None]:
    # Try without auth first for endpoints that are publicly exposed.
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 401:
            return response, "none"
    except requests.exceptions.RequestException:
        pass

    for username, password, source in auth_candidates:
        try:
            response = requests.get(
                url,
                auth=HTTPDigestAuth(username, password),
                timeout=10,
            )
        except requests.exceptions.RequestException:
            continue

        if response.status_code != 403:
            return response, source

    return None, None


def _parse_body_preview(response: requests.Response) -> str:
    body = response.text.strip().replace("\n", " ")
    if not body:
        return "<empty>"
    return body[:400]


def main() -> int:
    try:
        cfg = _load_ultimaker_cfg()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        print("Run: python3 manual_tests/ultimaker_pair_once.py")
        return 1

    base_url = f"http://{cfg['host'].rstrip('/')}"
    auth_candidates = [(cfg["username"], cfg["password"], "username")]
    if cfg.get("pairing_id") and cfg["pairing_id"] != cfg["username"]:
        auth_candidates.append((cfg["pairing_id"], cfg["password"], "pairing_id"))

    endpoints = [
        ("printer", f"{base_url}/api/v1/printer"),
        ("print_job", f"{base_url}/api/v1/print_job"),
        ("print_job_state", f"{base_url}/api/v1/print_job/state"),
    ]

    overall_ok = False

    for label, url in endpoints:
        print(f"[INFO] GET {label}: {url}")
        response, auth_source = _request_with_auth_fallback(url, auth_candidates)

        if response is None:
            print("[ERROR] Request failed for all auth options.")
            continue

        if auth_source and auth_source != "none":
            print(f"[INFO] Digest auth succeeded using {auth_source} credentials.")

        print(f"[INFO] HTTP {response.status_code}")

        if 200 <= response.status_code < 300:
            overall_ok = True
            try:
                payload = response.json()
                print(json.dumps(payload, indent=2)[:2000])
            except json.JSONDecodeError:
                print(response.text.strip()[:1200] or "<empty>")
            continue

        print(f"[WARN] Response body: {_parse_body_preview(response)}")

    if overall_ok:
        print("[OK] Ultimaker status endpoint check succeeded.")
        return 0

    print("[ERROR] No Ultimaker status endpoint returned success.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
