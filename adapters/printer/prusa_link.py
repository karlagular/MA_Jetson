import time

import requests
from requests.auth import HTTPDigestAuth

from ports.printer import PrinterPort


class PrusaAdapter(PrinterPort):
    """Adapter for Prusa printers via PrusaLink REST API."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._base_url = cfg["url"].rstrip("/")
        self._username = cfg.get("username")
        self._password = cfg.get("password")
        self._api_key = cfg.get("api_key")

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send an authenticated request (Digest first, Basic fallback)."""
        timeout_seconds = 10
        headers = kwargs.pop("headers", {})
        if (self._api_key
                and not str(self._api_key).startswith("OPTIONAL_")
                and "YOUR_" not in str(self._api_key)):
            headers["X-Api-Key"] = self._api_key

        if self._username and self._password:
            response = requests.request(
                method, url,
                auth=HTTPDigestAuth(self._username, self._password),
                headers=headers, timeout=timeout_seconds, **kwargs,
            )
            if response.status_code == 401:
                response = requests.request(
                    method, url,
                    auth=(self._username, self._password),
                    headers=headers, timeout=timeout_seconds, **kwargs,
                )
            return response

        return requests.request(
            method, url,
            headers=headers, timeout=timeout_seconds, **kwargs,
        )

    def _fetch_status_json(self) -> dict | None:
        try:
            response = self._request("GET", self._base_url + "/api/v1/status")
            if not (200 <= response.status_code < 300):
                return None
            return response.json()
        except Exception:
            return None

    @staticmethod
    def _status_indicates_paused(status: dict | None) -> bool:
        if not status:
            return False
        text = str(status).lower()
        return any(t in text for t in ("paused", "pausing", "state_paused"))

    @staticmethod
    def _status_indicates_active(status: dict | None) -> bool:
        if not status:
            return False
        text = str(status).lower()
        return any(t in text for t in (
            "printing", "paused", "pausing", "resuming",
            "state_printing", "state_paused",
        ))

    # ------------------------------------------------------------------
    def check_status(self) -> bool:
        return self._fetch_status_json() is not None

    def pause(self) -> None:
        baseline_status = self._fetch_status_json()
        baseline_paused = self._status_indicates_paused(baseline_status)

        candidates = [
            ("POST", self._base_url + "/api/job", {"command": "pause", "action": "pause"}),
            ("POST", self._base_url + "/api/v1/job/pause", None),
            ("POST", self._base_url + "/api/v1/job", {"command": "pause"}),
        ]

        for method, url, payload in candidates:
            kwargs = {}
            if payload is not None:
                kwargs["json"] = payload
            r = self._request(method, url, **kwargs)
            if 200 <= r.status_code < 300:
                print(f"[PrinterControl] Prusa pause: HTTP {r.status_code} via {url}")
                return

            time.sleep(1.0)
            current_status = self._fetch_status_json()
            if self._status_indicates_paused(current_status) and not baseline_paused:
                print(
                    f"[PrinterControl] Prusa pause took effect via {url} "
                    f"despite HTTP {r.status_code}"
                )
                return

        print("[PrinterControl] Prusa pause failed on all known endpoints")

    def stop(self) -> None:
        baseline_status = self._fetch_status_json()
        baseline_active = self._status_indicates_active(baseline_status)

        candidates = [
            ("POST", self._base_url + "/api/job", {"command": "cancel"}),
            ("DELETE", self._base_url + "/api/v1/job", None),
            ("POST", self._base_url + "/api/v1/job", {"command": "cancel"}),
        ]

        for method, url, payload in candidates:
            kwargs = {}
            if payload is not None:
                kwargs["json"] = payload
            r = self._request(method, url, **kwargs)
            if 200 <= r.status_code < 300:
                print(f"[PrinterControl] Prusa stop: HTTP {r.status_code} via {url}")
                return

            time.sleep(1.0)
            current_status = self._fetch_status_json()
            current_active = self._status_indicates_active(current_status)
            if baseline_active and not current_active:
                print(
                    f"[PrinterControl] Prusa stop took effect via {url} "
                    f"despite HTTP {r.status_code}"
                )
                return

        print("[PrinterControl] Prusa stop failed on all known endpoints")

    def resume(self) -> None:
        candidates = [
            ("POST", self._base_url + "/api/job", {"command": "pause", "action": "resume"}),
            ("POST", self._base_url + "/api/v1/job/resume", None),
            ("POST", self._base_url + "/api/v1/job", {"command": "resume"}),
        ]

        for method, url, payload in candidates:
            kwargs = {}
            if payload is not None:
                kwargs["json"] = payload
            r = self._request(method, url, **kwargs)
            if 200 <= r.status_code < 300:
                print(f"[PrinterControl] Prusa resume: HTTP {r.status_code} via {url}")
                return

        print("[PrinterControl] Prusa resume failed on all known endpoints")
