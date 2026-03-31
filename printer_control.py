import json
import os
import ssl
import threading
import time

import requests
from requests.auth import HTTPDigestAuth

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "machine_config.json")
_BAMBU_ACTIVE_STATES = {"RUNNING", "PAUSE", "PAUSED", "PAUSING", "RESUMING", "PREPARE"}


def check_printer_status(machine: str) -> bool:
    """Check once whether the selected printer is reachable. Returns True if available."""
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)[machine]
    except FileNotFoundError:
        print(f"[PrinterControl] machine_config.json not found at {_CONFIG_PATH}")
        return False
    except KeyError:
        print(f"[PrinterControl] No config entry for machine '{machine}'")
        return False

    try:
        if machine == "RatRig":
            return _status_klipper(cfg)
        elif machine == "Bambulab":
            return _status_bambulab(cfg)
        elif machine == "Prusa":
            return _status_prusa(cfg)
        elif machine == "Ultimaker":
            return _status_ultimaker(cfg)
        else:
            print(f"[PrinterControl] Unknown machine: '{machine}'")
            return False
    except Exception as e:
        print(f"[PrinterControl] Status check failed for '{machine}': {e}")
        return False


def pause_print(machine: str) -> None:
    """Non-blocking: sends the pause command in a daemon thread."""
    threading.Thread(target=_run_pause, args=(machine,), daemon=True).start()


def stop_print(machine: str) -> None:
    """Non-blocking: sends the stop command in a daemon thread."""
    threading.Thread(target=_run_stop, args=(machine,), daemon=True).start()


def resume_print(machine: str) -> None:
    """Non-blocking: sends the resume command in a daemon thread."""
    threading.Thread(target=_run_resume, args=(machine,), daemon=True).start()


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
            _pause_klipper(cfg)
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
            _stop_klipper(cfg)
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


def _run_resume(machine: str) -> None:
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
            _resume_klipper(cfg)
        elif machine == "Bambulab":
            _resume_bambulab(cfg)
        elif machine == "Prusa":
            _resume_prusa(cfg)
        elif machine == "Ultimaker":
            _resume_ultimaker(cfg)
        else:
            print(f"[PrinterControl] Unknown machine: '{machine}'")
    except Exception as e:
        print(f"[PrinterControl] Failed to resume '{machine}': {e}")


def _status_klipper(cfg: dict) -> bool:
    base = _klipper_base_url(cfg)
    r = requests.get(f"{base}/printer/objects/query?print_stats", timeout=5)
    return 200 <= r.status_code < 300


def _status_bambulab(cfg: dict) -> bool:
    import paho.mqtt.client as mqtt

    connected = threading.Event()
    report_received = threading.Event()
    request_topic = f"device/{cfg['serial']}/request"
    report_topic = f"device/{cfg['serial']}/report"

    def on_connect(client, _ud, _flags, rc):
        if rc == 0:
            connected.set()
            client.subscribe(report_topic)
            status_req = {
                "pushing": {
                    "sequence_id": _bambu_new_sequence_id(),
                    "command": "pushall",
                }
            }
            client.publish(request_topic, json.dumps(status_req))

    def on_message(_client, _ud, _msg):
        report_received.set()

    client = mqtt.Client()
    client.username_pw_set("bblp", cfg["access_code"])
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(cfg["host"], 8883, keepalive=15)
        client.loop_start()
        if not connected.wait(timeout=6):
            return False
        return report_received.wait(timeout=6)
    except Exception:
        return False
    finally:
        client.loop_stop()
        client.disconnect()


def _status_prusa(cfg: dict) -> bool:
    return _fetch_prusa_status_json(cfg) is not None


def _status_ultimaker(cfg: dict) -> bool:
    url = f"http://{cfg['host'].rstrip('/')}/api/v1/print_job/state"
    r = requests.get(url, timeout=5)
    return 200 <= r.status_code < 300


def _resume_klipper(cfg: dict) -> None:
    # Klipper Moonraker — POST /printer/print/resume
    base = _klipper_base_url(cfg)
    url = f"{base}/printer/print/resume"
    r = requests.post(url, timeout=10)
    if 200 <= r.status_code < 300:
        print(f"[PrinterControl] RatRig(Klipper) resume: HTTP {r.status_code}")
        return
    print(f"[PrinterControl] RatRig(Klipper) resume failed: HTTP {r.status_code}")


def _resume_bambulab(cfg: dict) -> None:
    import paho.mqtt.client as mqtt

    request_topic = f"device/{cfg['serial']}/request"
    report_topic = f"device/{cfg['serial']}/report"

    latest_state = {"value": None}
    report_event = threading.Event()

    def on_connect(client, _userdata, _flags, rc):
        if rc != 0:
            print(f"[PrinterControl] Bambulab MQTT connect failed with rc={rc}")
            return
        client.subscribe(report_topic)

    def on_message(_client, _userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return
        state = _bambu_find_first_key(payload, {"gcode_state", "print_state", "state"})
        if state:
            latest_state["value"] = state
        report_event.set()

    client = mqtt.Client()
    client.username_pw_set("bblp", cfg["access_code"])
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg["host"], 8883, keepalive=15)
    client.loop_start()

    try:
        resume_request = {
            "print": {
                "sequence_id": _bambu_new_sequence_id(),
                "command": "resume",
            }
        }
        client.publish(request_topic, json.dumps(resume_request))

        deadline = time.time() + 15.0
        while time.time() < deadline:
            if latest_state["value"] and latest_state["value"].strip().upper() == "RUNNING":
                print(f"[PrinterControl] Bambulab resume confirmed (state={latest_state['value']!r})")
                return

            report_event.wait(timeout=0.5)
            report_event.clear()

        print(f"[PrinterControl] Bambulab resume not confirmed (state={latest_state['value']!r})")
    finally:
        client.loop_stop()
        client.disconnect()


def _resume_prusa(cfg: dict) -> None:
    # PrusaLink resume endpoints vary by build; use known working order.
    base_url = cfg["url"].rstrip("/")

    candidates = [
        ("POST", base_url + "/api/job", {"command": "pause", "action": "resume"}),
        ("POST", base_url + "/api/v1/job/resume", None),
        ("POST", base_url + "/api/v1/job", {"command": "resume"}),
    ]

    for method, url, payload in candidates:
        kwargs = {}
        if payload is not None:
            kwargs["json"] = payload
        r = _prusa_request_with_auth(cfg, method, url, **kwargs)
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] Prusa resume: HTTP {r.status_code} via {url}")
            return

    print("[PrinterControl] Prusa resume failed on all known endpoints")


def _resume_ultimaker(cfg: dict) -> None:
    # Ultimaker REST API — PUT /api/v1/print_job/state {"target": "print"}
    url = f"http://{cfg['host'].rstrip('/')}/api/v1/print_job/state"

    r = _ultimaker_request_with_auth(cfg, "PUT", url, json={"target": "print"})
    if 200 <= r.status_code < 300:
        print(f"[PrinterControl] Ultimaker resume: HTTP {r.status_code}")
        return

    time.sleep(1.0)
    current_state = _fetch_ultimaker_state(cfg)
    if current_state in {"printing", "resuming"}:
        print(
            f"[PrinterControl] Ultimaker resume took effect despite HTTP {r.status_code}"
        )
        return

    print(f"[PrinterControl] Ultimaker resume failed: HTTP {r.status_code}")


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


def _klipper_base_url(cfg: dict) -> str:
    """Resolve Moonraker base URL from config."""
    base = cfg.get("moonraker_url") or cfg.get("url") or cfg.get("host")
    if not base:
        raise ValueError("RatRig config requires 'moonraker_url' (or 'url'/'host')")
    if not str(base).startswith(("http://", "https://")):
        base = "http://" + str(base)
    return str(base).rstrip("/")


def _pause_klipper(cfg: dict) -> None:
    # Klipper Moonraker — POST /printer/print/pause
    base = _klipper_base_url(cfg)
    url = f"{base}/printer/print/pause"
    r = requests.post(url, timeout=10)
    if 200 <= r.status_code < 300:
        print(f"[PrinterControl] RatRig(Klipper) pause: HTTP {r.status_code}")
        return
    print(f"[PrinterControl] RatRig(Klipper) pause failed: HTTP {r.status_code}")


def _stop_klipper(cfg: dict) -> None:
    # Klipper Moonraker — POST /printer/print/cancel
    base = _klipper_base_url(cfg)
    url = f"{base}/printer/print/cancel"
    r = requests.post(url, timeout=10)
    if 200 <= r.status_code < 300:
        print(f"[PrinterControl] RatRig(Klipper) cancel: HTTP {r.status_code}")
        return
    print(f"[PrinterControl] RatRig(Klipper) cancel failed: HTTP {r.status_code}")


def _bambu_new_sequence_id() -> str:
    return str(time.time_ns())


def _bambu_find_first_key(node, target_keys: set[str]):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in target_keys and isinstance(v, str):
                return v
            found = _bambu_find_first_key(v, target_keys)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _bambu_find_first_key(item, target_keys)
            if found:
                return found
    return None


def _bambu_is_paused_state(state: str | None) -> bool:
    if not state:
        return False
    return state.strip().upper() in {"PAUSE", "PAUSED", "PAUSING"}


def _bambu_is_active_state(state: str | None) -> bool:
    if not state:
        return False
    return state.strip().upper() in _BAMBU_ACTIVE_STATES


def _stop_bambulab(cfg: dict) -> None:
    # Bambulab local MQTT broker on port 8883 (TLS, self-signed cert).
    # Uses minimal accepted command schema and report-based confirmation.
    import paho.mqtt.client as mqtt

    request_topic = f"device/{cfg['serial']}/request"
    report_topic = f"device/{cfg['serial']}/report"

    latest_state = {"value": None}
    latest_payload = {"value": None}
    latest_print_result = {"value": None}
    latest_print_reason = {"value": None}
    report_event = threading.Event()

    def on_connect(client, _userdata, _flags, rc):
        if rc != 0:
            print(f"[PrinterControl] Bambulab MQTT connect failed with rc={rc}")
            return
        client.subscribe(report_topic)

    def on_message(_client, _userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return

        latest_payload["value"] = payload
        state = _bambu_find_first_key(payload, {"gcode_state", "print_state", "state"})
        if state:
            latest_state["value"] = state

        if isinstance(payload, dict) and isinstance(payload.get("print"), dict):
            p = payload["print"]
            if isinstance(p.get("result"), str):
                latest_print_result["value"] = p.get("result")
            if isinstance(p.get("reason"), str):
                latest_print_reason["value"] = p.get("reason")

        report_event.set()

    client = mqtt.Client()
    client.username_pw_set("bblp", cfg["access_code"])
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg["host"], 8883, keepalive=10)
    client.loop_start()

    try:
        status_request = {
            "pushing": {
                "sequence_id": _bambu_new_sequence_id(),
                "command": "pushall",
            }
        }
        client.publish(request_topic, json.dumps(status_request))
        report_event.wait(timeout=6.0)
        baseline_state = latest_state["value"]

        if not _bambu_is_active_state(baseline_state):
            print("[PrinterControl] Bambulab stop skipped: no active print job")
            return

        stop_request = {
            "print": {
                "sequence_id": _bambu_new_sequence_id(),
                "command": "stop",
            }
        }
        latest_print_result["value"] = None
        latest_print_reason["value"] = None
        client.publish(request_topic, json.dumps(stop_request))

        deadline = time.time() + 20.0
        while time.time() < deadline:
            if not _bambu_is_active_state(latest_state["value"]):
                print(f"[PrinterControl] Bambulab stop confirmed (state={latest_state['value']!r})")
                return

            result = (latest_print_result["value"] or "").strip().upper()
            reason = (latest_print_reason["value"] or "").strip()
            if result == "FAIL":
                print(f"[PrinterControl] Bambulab stop failed: reason={reason!r}")
                return

            report_event.wait(timeout=0.5)
            report_event.clear()

        print(f"[PrinterControl] Bambulab stop not confirmed (state={latest_state['value']!r})")
    finally:
        client.loop_stop()
        client.disconnect()


def _pause_bambulab(cfg: dict) -> None:
    # Bambulab local MQTT broker on port 8883 (TLS, self-signed cert).
    # Uses minimal accepted command schema and report-based confirmation.
    import paho.mqtt.client as mqtt

    request_topic = f"device/{cfg['serial']}/request"
    report_topic = f"device/{cfg['serial']}/report"

    latest_state = {"value": None}
    latest_payload = {"value": None}
    latest_print_result = {"value": None}
    latest_print_reason = {"value": None}
    report_event = threading.Event()

    def on_connect(client, _userdata, _flags, rc):
        if rc != 0:
            print(f"[PrinterControl] Bambulab MQTT connect failed with rc={rc}")
            return
        client.subscribe(report_topic)

    def on_message(_client, _userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return

        latest_payload["value"] = payload
        state = _bambu_find_first_key(payload, {"gcode_state", "print_state", "state"})
        if state:
            latest_state["value"] = state

        if isinstance(payload, dict) and isinstance(payload.get("print"), dict):
            p = payload["print"]
            if isinstance(p.get("result"), str):
                latest_print_result["value"] = p.get("result")
            if isinstance(p.get("reason"), str):
                latest_print_reason["value"] = p.get("reason")

        report_event.set()

    client = mqtt.Client()
    client.username_pw_set("bblp", cfg["access_code"])
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg["host"], 8883, keepalive=10)
    client.loop_start()

    try:
        status_request = {
            "pushing": {
                "sequence_id": _bambu_new_sequence_id(),
                "command": "pushall",
            }
        }
        client.publish(request_topic, json.dumps(status_request))
        report_event.wait(timeout=6.0)
        baseline_state = latest_state["value"]

        if _bambu_is_paused_state(baseline_state):
            print("[PrinterControl] Bambulab pause skipped: already paused")
            return

        pause_request = {
            "print": {
                "sequence_id": _bambu_new_sequence_id(),
                "command": "pause",
            }
        }
        latest_print_result["value"] = None
        latest_print_reason["value"] = None
        client.publish(request_topic, json.dumps(pause_request))

        deadline = time.time() + 15.0
        while time.time() < deadline:
            if _bambu_is_paused_state(latest_state["value"]):
                print(f"[PrinterControl] Bambulab pause confirmed (state={latest_state['value']!r})")
                return

            result = (latest_print_result["value"] or "").strip().upper()
            reason = (latest_print_reason["value"] or "").strip()
            if result == "FAIL":
                print(f"[PrinterControl] Bambulab pause failed: reason={reason!r}")
                return

            report_event.wait(timeout=0.5)
            report_event.clear()

        print(f"[PrinterControl] Bambulab pause not confirmed (state={latest_state['value']!r})")
    finally:
        client.loop_stop()
        client.disconnect()


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
