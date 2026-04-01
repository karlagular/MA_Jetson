import json
import ssl
import threading
import time

from ports.printer import PrinterPort

_ACTIVE_STATES = {"RUNNING", "PAUSE", "PAUSED", "PAUSING", "RESUMING", "PREPARE"}
_PAUSED_STATES = {"PAUSE", "PAUSED", "PAUSING"}


def _new_sequence_id() -> str:
    return str(time.time_ns())


def _find_first_key(node, target_keys: set[str]):
    """Recursively search a JSON structure for the first string value whose key is in target_keys."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in target_keys and isinstance(v, str):
                return v
            found = _find_first_key(v, target_keys)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_first_key(item, target_keys)
            if found:
                return found
    return None


def _is_paused_state(state: str | None) -> bool:
    if not state:
        return False
    return state.strip().upper() in _PAUSED_STATES


def _is_active_state(state: str | None) -> bool:
    if not state:
        return False
    return state.strip().upper() in _ACTIVE_STATES


class BambulabAdapter(PrinterPort):
    """Adapter for Bambulab printers via local MQTT broker (TLS, port 8883)."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._host = cfg["host"]
        self._access_code = cfg["access_code"]
        self._serial = cfg["serial"]
        self._request_topic = f"device/{self._serial}/request"
        self._report_topic = f"device/{self._serial}/report"

    def _create_client(self):
        import paho.mqtt.client as mqtt

        client = mqtt.Client()
        client.username_pw_set("bblp", self._access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        return client

    # ------------------------------------------------------------------
    # check_status
    # ------------------------------------------------------------------
    def check_status(self) -> bool:
        import paho.mqtt.client as mqtt

        connected = threading.Event()
        report_received = threading.Event()

        def on_connect(client, _ud, _flags, rc):
            if rc == 0:
                connected.set()
                client.subscribe(self._report_topic)
                status_req = {
                    "pushing": {
                        "sequence_id": _new_sequence_id(),
                        "command": "pushall",
                    }
                }
                client.publish(self._request_topic, json.dumps(status_req))

        def on_message(_client, _ud, _msg):
            report_received.set()

        client = self._create_client()
        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(self._host, 8883, keepalive=15)
            client.loop_start()
            if not connected.wait(timeout=6):
                return False
            return report_received.wait(timeout=6)
        except Exception:
            return False
        finally:
            client.loop_stop()
            client.disconnect()

    # ------------------------------------------------------------------
    # pause
    # ------------------------------------------------------------------
    def pause(self) -> None:
        client = self._create_client()

        latest_state = {"value": None}
        latest_print_result = {"value": None}
        latest_print_reason = {"value": None}
        report_event = threading.Event()

        def on_connect(c, _userdata, _flags, rc):
            if rc != 0:
                print(f"[PrinterControl] Bambulab MQTT connect failed with rc={rc}")
                return
            c.subscribe(self._report_topic)

        def on_message(_c, _userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                return
            state = _find_first_key(payload, {"gcode_state", "print_state", "state"})
            if state:
                latest_state["value"] = state
            if isinstance(payload, dict) and isinstance(payload.get("print"), dict):
                p = payload["print"]
                if isinstance(p.get("result"), str):
                    latest_print_result["value"] = p["result"]
                if isinstance(p.get("reason"), str):
                    latest_print_reason["value"] = p["reason"]
            report_event.set()

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self._host, 8883, keepalive=10)
        client.loop_start()

        try:
            # Query current state first
            client.publish(self._request_topic, json.dumps({
                "pushing": {"sequence_id": _new_sequence_id(), "command": "pushall"}
            }))
            report_event.wait(timeout=6.0)

            if _is_paused_state(latest_state["value"]):
                print("[PrinterControl] Bambulab pause skipped: already paused")
                return

            latest_print_result["value"] = None
            latest_print_reason["value"] = None
            client.publish(self._request_topic, json.dumps({
                "print": {"sequence_id": _new_sequence_id(), "command": "pause"}
            }))

            deadline = time.time() + 15.0
            while time.time() < deadline:
                if _is_paused_state(latest_state["value"]):
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

    # ------------------------------------------------------------------
    # stop
    # ------------------------------------------------------------------
    def stop(self) -> None:
        client = self._create_client()

        latest_state = {"value": None}
        latest_print_result = {"value": None}
        latest_print_reason = {"value": None}
        report_event = threading.Event()

        def on_connect(c, _userdata, _flags, rc):
            if rc != 0:
                print(f"[PrinterControl] Bambulab MQTT connect failed with rc={rc}")
                return
            c.subscribe(self._report_topic)

        def on_message(_c, _userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                return
            state = _find_first_key(payload, {"gcode_state", "print_state", "state"})
            if state:
                latest_state["value"] = state
            if isinstance(payload, dict) and isinstance(payload.get("print"), dict):
                p = payload["print"]
                if isinstance(p.get("result"), str):
                    latest_print_result["value"] = p["result"]
                if isinstance(p.get("reason"), str):
                    latest_print_reason["value"] = p["reason"]
            report_event.set()

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self._host, 8883, keepalive=10)
        client.loop_start()

        try:
            client.publish(self._request_topic, json.dumps({
                "pushing": {"sequence_id": _new_sequence_id(), "command": "pushall"}
            }))
            report_event.wait(timeout=6.0)
            baseline_state = latest_state["value"]

            if not _is_active_state(baseline_state):
                print("[PrinterControl] Bambulab stop skipped: no active print job")
                return

            latest_print_result["value"] = None
            latest_print_reason["value"] = None
            client.publish(self._request_topic, json.dumps({
                "print": {"sequence_id": _new_sequence_id(), "command": "stop"}
            }))

            deadline = time.time() + 20.0
            while time.time() < deadline:
                if not _is_active_state(latest_state["value"]):
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

    # ------------------------------------------------------------------
    # resume
    # ------------------------------------------------------------------
    def resume(self) -> None:
        client = self._create_client()

        latest_state = {"value": None}
        report_event = threading.Event()

        def on_connect(c, _userdata, _flags, rc):
            if rc != 0:
                print(f"[PrinterControl] Bambulab MQTT connect failed with rc={rc}")
                return
            c.subscribe(self._report_topic)

        def on_message(_c, _userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                return
            state = _find_first_key(payload, {"gcode_state", "print_state", "state"})
            if state:
                latest_state["value"] = state
            report_event.set()

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self._host, 8883, keepalive=15)
        client.loop_start()

        try:
            client.publish(self._request_topic, json.dumps({
                "print": {"sequence_id": _new_sequence_id(), "command": "resume"}
            }))

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
