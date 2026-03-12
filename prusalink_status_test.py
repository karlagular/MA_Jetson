#!/usr/bin/env python3
"""One-shot PrusaLink status check for a Prusa CORE One+ printer."""

import json
import sys

import requests
from requests.auth import HTTPDigestAuth

PRUSALINK_HOST = "192.168.226.67"
PRUSALINK_USER = "maker"
PRUSALINK_PASSWORD = "jhv88m3BERCuWXz"
STATUS_URL = f"http://{PRUSALINK_HOST}/api/v1/status"


def fetch_status_once() -> dict:
    """Fetch printer status once from PrusaLink and return parsed JSON."""
    timeout_seconds = 10

    # PrusaLink commonly uses HTTP Digest auth; try this first.
    response = requests.get(
        STATUS_URL,
        auth=HTTPDigestAuth(PRUSALINK_USER, PRUSALINK_PASSWORD),
        timeout=timeout_seconds,
    )

    # Some setups may still accept Basic auth; use it as a fallback.
    if response.status_code == 401:
        response = requests.get(
            STATUS_URL,
            auth=(PRUSALINK_USER, PRUSALINK_PASSWORD),
            timeout=timeout_seconds,
        )

    response.raise_for_status()
    return response.json()


def main() -> int:
    try:
        status = fetch_status_once()
    except requests.exceptions.RequestException as exc:
        print(f"[ERROR] Request failed: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Response was not valid JSON: {exc}")
        return 1

    print("[OK] PrusaLink status retrieved successfully.")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
