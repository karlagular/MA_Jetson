#!/usr/bin/env python3
"""One-shot PrusaLink stop command test for a Prusa CORE One+ printer."""

import sys
import time

import requests
from requests.auth import HTTPDigestAuth

PRUSALINK_HOST = "10.75.100.38"
PRUSALINK_USER = "maker"
PRUSALINK_PASSWORD = "jhv88m3BERCuWXz"
BASE_URL = f"http://{PRUSALINK_HOST}"


def _request_with_auth(method: str, url: str, **kwargs) -> requests.Response:
    """Send one request with Digest auth, then fallback to Basic on 401."""
    timeout_seconds = 10

    response = requests.request(
        method,
        url,
        auth=HTTPDigestAuth(PRUSALINK_USER, PRUSALINK_PASSWORD),
        timeout=timeout_seconds,
        **kwargs,
    )

    if response.status_code == 401:
        response = requests.request(
            method,
            url,
            auth=(PRUSALINK_USER, PRUSALINK_PASSWORD),
            timeout=timeout_seconds,
            **kwargs,
        )

    return response


def _fetch_status_json() -> dict | None:
    """Fetch /api/v1/status and return JSON, or None if unavailable."""
    try:
        response = _request_with_auth("GET", f"{BASE_URL}/api/v1/status")
        if not (200 <= response.status_code < 300):
            return None
        return response.json()
    except Exception:
        return None


def _status_indicates_active_job(status: dict | None) -> bool:
    """Best-effort detection of an active print job from status payload."""
    if not status:
        return False

    text = str(status).lower()
    active_tokens = (
        "printing",
        "paused",
        "pausing",
        "resuming",
        "state_printing",
        "state_paused",
    )
    return any(token in text for token in active_tokens)


def stop_print_once() -> int:
    """Try known stop/cancel endpoints and return 0 on success."""
    baseline_status = _fetch_status_json()
    baseline_active = _status_indicates_active_job(baseline_status)

    candidates = [
        # Known working family for this printer (same style as pause test).
        ("POST", f"{BASE_URL}/api/job", {"command": "cancel"}),
        # Native PrusaLink endpoint used to cancel active job.
        ("DELETE", f"{BASE_URL}/api/v1/job", None),
        # Alternative command-style endpoint.
        ("POST", f"{BASE_URL}/api/v1/job", {"command": "cancel"}),
    ]

    for method, url, payload in candidates:
        try:
            kwargs = {}
            if payload is not None:
                kwargs["json"] = payload
            response = _request_with_auth(method, url, **kwargs)
        except requests.exceptions.RequestException as exc:
            print(f"[WARN] {method} {url} failed: {exc}")
            continue

        if 200 <= response.status_code < 300:
            print(f"[OK] Stop command accepted via {method} {url} (HTTP {response.status_code})")
            return 0

        # Some PrusaLink variants may still apply cancel despite non-2xx.
        time.sleep(1.0)
        current_status = _fetch_status_json()
        current_active = _status_indicates_active_job(current_status)
        if baseline_active and not current_active:
            print(
                f"[OK] Stop took effect after {method} {url} "
                f"despite HTTP {response.status_code}"
            )
            return 0

        body_preview = response.text.strip().replace("\n", " ")
        body_preview = body_preview[:240] if body_preview else "<empty>"
        print(
            f"[WARN] {method} {url} returned HTTP {response.status_code}; "
            f"response: {body_preview}"
        )

    print("[ERROR] Could not stop print job with tested PrusaLink endpoints.")
    return 1


def main() -> int:
    return stop_print_once()


if __name__ == "__main__":
    sys.exit(main())
