import json
import os
import ssl
import threading

import requests

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
    # PrusaLink REST API — DELETE /api/v1/job
    url = cfg["url"].rstrip("/") + "/api/v1/job"
    r = requests.delete(
        url,
        headers={"X-Api-Key": cfg["api_key"]},
        timeout=10,
    )
    print(f"[PrinterControl] Prusa stop: HTTP {r.status_code}")


def _pause_prusa(cfg: dict) -> None:
    # PrusaLink pause endpoints vary by build; try known options.
    base_url = cfg["url"].rstrip("/")
    headers = {"X-Api-Key": cfg["api_key"]}
    candidates = [
        ("post", base_url + "/api/job", {"command": "pause", "action": "pause"}),
        ("post", base_url + "/api/v1/job/pause", None),
        ("post", base_url + "/api/v1/job", {"command": "pause"}),
    ]

    for method, url, payload in candidates:
        kwargs = {"headers": headers, "timeout": 10}
        if payload is not None:
            kwargs["json"] = payload
        r = requests.request(method=method, url=url, **kwargs)
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] Prusa pause: HTTP {r.status_code} via {url}")
            return

    print("[PrinterControl] Prusa pause failed on all known endpoints")


def _stop_ultimaker(cfg: dict) -> None:
    # Ultimaker REST API — PUT /api/v1/print_job/state {"target": "abort"}
    from requests.auth import HTTPDigestAuth

    url = f"http://{cfg['host'].rstrip('/')}/api/v1/print_job/state"
    r = requests.put(
        url,
        json={"target": "abort"},
        auth=HTTPDigestAuth(cfg["username"], cfg["password"]),
        timeout=10,
    )
    print(f"[PrinterControl] Ultimaker abort: HTTP {r.status_code}")


def _pause_ultimaker(cfg: dict) -> None:
    # Ultimaker REST API — PUT /api/v1/print_job/state {"target": "pause"}
    from requests.auth import HTTPDigestAuth

    url = f"http://{cfg['host'].rstrip('/')}/api/v1/print_job/state"
    r = requests.put(
        url,
        json={"target": "pause"},
        auth=HTTPDigestAuth(cfg["username"], cfg["password"]),
        timeout=10,
    )
    print(f"[PrinterControl] Ultimaker pause: HTTP {r.status_code}")
