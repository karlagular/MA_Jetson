import time

import requests
from requests.auth import HTTPDigestAuth

from legacy.printer_control.ports import PrinterPort


class UltimakerAdapter(PrinterPort):
    """Adapter for Ultimaker printers via REST API."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._host = cfg["host"].rstrip("/")
        self._username = cfg.get("username")
        self._pairing_id = cfg.get("pairing_id")
        self._password = cfg.get("password")

    def _state_url(self) -> str:
        return f"http://{self._host}/api/v1/print_job/state"

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send a Digest-authenticated request with pairing_id fallback on 403."""
        timeout_seconds = 10
        auth_candidates = []
        if self._username and self._password:
            auth_candidates.append((self._username, self._password, "username"))
        if self._pairing_id and self._password and self._pairing_id != self._username:
            auth_candidates.append((self._pairing_id, self._password, "pairing_id"))

        if not auth_candidates:
            raise ValueError("Ultimaker config missing username/password or pairing_id/password")

        last_response = None
        for user, pwd, source in auth_candidates:
            response = requests.request(
                method, url,
                auth=HTTPDigestAuth(user, pwd),
                timeout=timeout_seconds, **kwargs,
            )
            last_response = response
            if response.status_code != 403:
                if source != "username":
                    print(f"[PrinterControl] Ultimaker auth fallback succeeded via {source}")
                return response

        return last_response

    def _fetch_state(self) -> str | None:
        try:
            r = requests.get(self._state_url(), timeout=10)
            if not (200 <= r.status_code < 300):
                return None
            return r.text.strip().strip('"').lower()
        except Exception:
            return None

    @staticmethod
    def _is_paused(state: str | None) -> bool:
        return state in {"paused", "pausing"} if state else False

    @staticmethod
    def _is_active(state: str | None) -> bool:
        return state in {"printing", "paused", "pausing", "resuming"} if state else False

    # ------------------------------------------------------------------
    def check_status(self) -> bool:
        r = requests.get(self._state_url(), timeout=5)
        return 200 <= r.status_code < 300

    def pause(self) -> None:
        baseline_state = self._fetch_state()
        r = self._request("PUT", self._state_url(), json={"target": "pause"})
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] Ultimaker pause: HTTP {r.status_code}")
            return

        time.sleep(1.0)
        current_state = self._fetch_state()
        if not self._is_paused(baseline_state) and self._is_paused(current_state):
            print(
                f"[PrinterControl] Ultimaker pause took effect despite HTTP {r.status_code}"
            )
            return

        print(f"[PrinterControl] Ultimaker pause failed: HTTP {r.status_code}")

    def stop(self) -> None:
        baseline_state = self._fetch_state()
        r = self._request("PUT", self._state_url(), json={"target": "abort"})
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] Ultimaker abort: HTTP {r.status_code}")
            return

        time.sleep(1.0)
        current_state = self._fetch_state()
        if self._is_active(baseline_state) and not self._is_active(current_state):
            print(
                f"[PrinterControl] Ultimaker abort took effect despite HTTP {r.status_code}"
            )
            return

        print(f"[PrinterControl] Ultimaker abort failed: HTTP {r.status_code}")

    def resume(self) -> None:
        r = self._request("PUT", self._state_url(), json={"target": "print"})
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] Ultimaker resume: HTTP {r.status_code}")
            return

        time.sleep(1.0)
        current_state = self._fetch_state()
        if current_state in {"printing", "resuming"}:
            print(
                f"[PrinterControl] Ultimaker resume took effect despite HTTP {r.status_code}"
            )
            return

        print(f"[PrinterControl] Ultimaker resume failed: HTTP {r.status_code}")
