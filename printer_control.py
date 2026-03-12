import json
import os
import ssl
import threading
import time

import requests
from requests.auth import HTTPDigestAuth

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "machine_config.json")


def pause_print(machine: str) -> None:
    """Non-blocking: sends the pause command in a daemon thread."""
    threading.Thread(target=_run_pause, args=(machine,), daemon=True).start()


def stop_print(machine: str) -> None:
    """Non-blocking: sends the stop command in a daemon thread."""
    threading.Thread(target=_run_stop, args=(machine,), daemon=True).start()


def _run_pause(machine: str) -> None:
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)[machine]
    except FileNotFoundError:
        print(f"[PrinterControl] machine_config.json not found at {_CONFIG_PATH}")
        return
    except KeyError:
        print(f"[PrinterControl] No config entry for machine '{machine}'")
        return

    try:
        if machine == "RatRig":
            _pause_octoprint(cfg)
        elif machine == "Bambulab":
            _pause_bambulab(cfg)
        elif machine == "Prusa":
            _pause_prusa(cfg)
        elif machine == "Ultimaker":
            _pause_ultimaker(cfg)
        else:
            print(f"[PrinterControl] Unknown machine: '{machine}'")
    except Exception as e:
        print(f"[PrinterControl] Failed to pause '{machine}': {e}")


def _run_stop(machine: str) -> None:
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)[machine]
    except FileNotFoundError:
        print(f"[PrinterControl] machine_config.json not found at {_CONFIG_PATH}")
        return
    except KeyError:
        print(f"[PrinterControl] No config entry for machine '{machine}'")
        return

    try:
        if machine == "RatRig":
            _stop_octoprint(cfg)
        elif machine == "Bambulab":
            _stop_bambulab(cfg)
        elif machine == "Prusa":
            _stop_prusa(cfg)
        elif machine == "Ultimaker":
            _stop_ultimaker(cfg)
        else:
            print(f"[PrinterControl] Unknown machine: '{machine}'")
    except Exception as e:
        print(f"[PrinterControl] Failed to stop '{machine}': {e}")


def _stop_octoprint(cfg: dict) -> None:
    # OctoPrint REST API — POST /api/job {"command": "cancel"}
    url = cfg["url"].rstrip("/") + "/api/job"
    r = requests.post(
        url,
        json={"command": "cancel"},
        headers={"X-Api-Key": cfg["api_key"]},
        timeout=10,
    )
    print(f"[PrinterControl] OctoPrint cancel: HTTP {r.status_code}")


def _pause_octoprint(cfg: dict) -> None:
    # OctoPrint REST API — POST /api/job {"command": "pause", "action": "pause"}
    url = cfg["url"].rstrip("/") + "/api/job"
    r = requests.post(
        url,
        json={"command": "pause", "action": "pause"},
        headers={"X-Api-Key": cfg["api_key"]},
        timeout=10,
    )
    print(f"[PrinterControl] OctoPrint pause: HTTP {r.status_code}")


def _stop_bambulab(cfg: dict) -> None:
    # Bambulab local MQTT broker on port 8883 (TLS, self-signed cert)
    import paho.mqtt.client as mqtt

    topic = f"device/{cfg['serial']}/request"
    payload = json.dumps({
        "print": {"sequence_id": "0", "command": "stop", "param": ""}
    })

    client = mqtt.Client()
    client.username_pw_set("bblp", cfg["access_code"])
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.connect(cfg["host"], 8883, keepalive=10)
    client.publish(topic, payload)
    client.loop(timeout=2.0)  # pump network once to flush the publish
    client.disconnect()
    print("[PrinterControl] Bambulab stop sent via MQTT")


def _pause_bambulab(cfg: dict) -> None:
    # Bambulab local MQTT broker on port 8883 (TLS, self-signed cert)
    import paho.mqtt.client as mqtt

    topic = f"device/{cfg['serial']}/request"
    payload = json.dumps({
        "print": {"sequence_id": "0", "command": "pause", "param": ""}
    })

    client = mqtt.Client()
    client.username_pw_set("bblp", cfg["access_code"])
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.connect(cfg["host"], 8883, keepalive=10)
    client.publish(topic, payload)
    client.loop(timeout=2.0)  # pump network once to flush the publish
    client.disconnect()
    print("[PrinterControl] Bambulab pause sent via MQTT")


def _stop_prusa(cfg: dict) -> None:
    # PrusaLink stop endpoints vary by build; use known working order.
    base_url = cfg["url"].rstrip("/")
    baseline_status = _fetch_prusa_status_json(cfg)
    baseline_active = _prusa_status_indicates_active_job(baseline_status)

    candidates = [
        ("POST", base_url + "/api/job", {"command": "cancel"}),
        ("DELETE", base_url + "/api/v1/job", None),
        ("POST", base_url + "/api/v1/job", {"command": "cancel"}),
    ]

    for method, url, payload in candidates:
        kwargs = {}
        if payload is not None:
            kwargs["json"] = payload
        r = _prusa_request_with_auth(cfg, method, url, **kwargs)
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] Prusa stop: HTTP {r.status_code} via {url}")
            return

        time.sleep(1.0)
        current_status = _fetch_prusa_status_json(cfg)
        current_active = _prusa_status_indicates_active_job(current_status)
        if baseline_active and not current_active:
            print(
                f"[PrinterControl] Prusa stop took effect via {url} "
                f"despite HTTP {r.status_code}"
            )
            return

    print("[PrinterControl] Prusa stop failed on all known endpoints")


def _pause_prusa(cfg: dict) -> None:
    # PrusaLink pause endpoints vary by build; use known working order.
    base_url = cfg["url"].rstrip("/")
    baseline_status = _fetch_prusa_status_json(cfg)
    baseline_paused = _prusa_status_indicates_paused(baseline_status)

    candidates = [
        ("POST", base_url + "/api/job", {"command": "pause", "action": "pause"}),
        ("POST", base_url + "/api/v1/job/pause", None),
        ("POST", base_url + "/api/v1/job", {"command": "pause"}),
    ]

    for method, url, payload in candidates:
        kwargs = {}
        if payload is not None:
            kwargs["json"] = payload
        r = _prusa_request_with_auth(cfg, method, url, **kwargs)
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] Prusa pause: HTTP {r.status_code} via {url}")
            return

        time.sleep(1.0)
        current_status = _fetch_prusa_status_json(cfg)
        currently_paused = _prusa_status_indicates_paused(current_status)
        if currently_paused and not baseline_paused:
            print(
                f"[PrinterControl] Prusa pause took effect via {url} "
                f"despite HTTP {r.status_code}"
            )
            return

    print("[PrinterControl] Prusa pause failed on all known endpoints")


def _prusa_request_with_auth(cfg: dict, method: str, url: str, **kwargs) -> requests.Response:
    """Use Digest auth first, then Basic auth fallback; include API key if configured."""
    timeout_seconds = 10
    username = cfg.get("username")
    password = cfg.get("password")
    headers = kwargs.pop("headers", {})
    api_key = cfg.get("api_key")
    if api_key and not str(api_key).startswith("OPTIONAL_") and "YOUR_" not in str(api_key):
        headers["X-Api-Key"] = api_key

    if username and password:
        response = requests.request(
            method,
            url,
            auth=HTTPDigestAuth(username, password),
            headers=headers,
            timeout=timeout_seconds,
            **kwargs,
        )
        if response.status_code == 401:
            response = requests.request(
                method,
                url,
                auth=(username, password),
                headers=headers,
                timeout=timeout_seconds,
                **kwargs,
            )
        return response

    return requests.request(
        method,
        url,
        headers=headers,
        timeout=timeout_seconds,
        **kwargs,
    )


def _fetch_prusa_status_json(cfg: dict) -> dict | None:
    """Fetch /api/v1/status and return JSON, or None if unavailable."""
    base_url = cfg["url"].rstrip("/")
    try:
        response = _prusa_request_with_auth(cfg, "GET", base_url + "/api/v1/status")
        if not (200 <= response.status_code < 300):
            return None
        return response.json()
    except Exception:
        return None


def _prusa_status_indicates_paused(status: dict | None) -> bool:
    """Best-effort paused detection from PrusaLink status payload."""
    if not status:
        return False

    text = str(status).lower()
    paused_tokens = ("paused", "pausing", "state_paused")
    return any(token in text for token in paused_tokens)


def _prusa_status_indicates_active_job(status: dict | None) -> bool:
    """Best-effort active-job detection from PrusaLink status payload."""
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


def _stop_ultimaker(cfg: dict) -> None:
    # Ultimaker REST API — PUT /api/v1/print_job/state {"target": "abort"}
    url = f"http://{cfg['host'].rstrip('/')}/api/v1/print_job/state"
    baseline_state = _fetch_ultimaker_state(cfg)

    r = _ultimaker_request_with_auth(cfg, "PUT", url, json={"target": "abort"})
    if 200 <= r.status_code < 300:
        print(f"[PrinterControl] Ultimaker abort: HTTP {r.status_code}")
        return

    # Some firmwares acknowledge state changes with delay. Confirm by state.
    time.sleep(1.0)
    current_state = _fetch_ultimaker_state(cfg)
    if _ultimaker_state_indicates_active(baseline_state) and not _ultimaker_state_indicates_active(current_state):
        print(
            f"[PrinterControl] Ultimaker abort took effect despite HTTP {r.status_code}"
        )
        return

    print(f"[PrinterControl] Ultimaker abort failed: HTTP {r.status_code}")


def _pause_ultimaker(cfg: dict) -> None:
    # Ultimaker REST API — PUT /api/v1/print_job/state {"target": "pause"}
    url = f"http://{cfg['host'].rstrip('/')}/api/v1/print_job/state"
    baseline_state = _fetch_ultimaker_state(cfg)

    r = _ultimaker_request_with_auth(cfg, "PUT", url, json={"target": "pause"})
    if 200 <= r.status_code < 300:
        print(f"[PrinterControl] Ultimaker pause: HTTP {r.status_code}")
        return

    # Match test-script behavior: verify pause via state endpoint.
    time.sleep(1.0)
    current_state = _fetch_ultimaker_state(cfg)
    if not _ultimaker_state_indicates_paused(baseline_state) and _ultimaker_state_indicates_paused(current_state):
        print(
            f"[PrinterControl] Ultimaker pause took effect despite HTTP {r.status_code}"
        )
        return

    print(f"[PrinterControl] Ultimaker pause failed: HTTP {r.status_code}")


def _ultimaker_request_with_auth(cfg: dict, method: str, url: str, **kwargs) -> requests.Response:
    """Try Ultimaker Digest auth with username, then pairing_id fallback on 403."""
    timeout_seconds = 10
    username = cfg.get("username")
    pairing_id = cfg.get("pairing_id")
    password = cfg.get("password")

    auth_candidates = []
    if username and password:
        auth_candidates.append((username, password, "username"))
    if pairing_id and password and pairing_id != username:
        auth_candidates.append((pairing_id, password, "pairing_id"))

    if not auth_candidates:
        raise ValueError("Ultimaker config missing username/password or pairing_id/password")

    last_response = None
    for user, pwd, source in auth_candidates:
        response = requests.request(
            method,
            url,
            auth=HTTPDigestAuth(user, pwd),
            timeout=timeout_seconds,
            **kwargs,
        )
        last_response = response
        if response.status_code != 403:
            if source != "username":
                print(f"[PrinterControl] Ultimaker auth fallback succeeded via {source}")
            return response

    return last_response


def _fetch_ultimaker_state(cfg: dict) -> str | None:
    """Fetch current Ultimaker print-job state string, e.g. 'printing'."""
    url = f"http://{cfg['host'].rstrip('/')}/api/v1/print_job/state"
    try:
        r = requests.get(url, timeout=10)
        if not (200 <= r.status_code < 300):
            return None
        return r.text.strip().strip('"').lower()
    except Exception:
        return None


def _ultimaker_state_indicates_paused(state: str | None) -> bool:
    if not state:
        return False
    return state in {"paused", "pausing"}


def _ultimaker_state_indicates_active(state: str | None) -> bool:
    if not state:
        return False
    return state in {"printing", "paused", "pausing", "resuming"}
