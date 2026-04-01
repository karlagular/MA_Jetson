"""Unit tests for printer adapters — isolated via mocked HTTP / MQTT."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch, call


# ======================================================================
# KlipperAdapter (HTTP via requests)
# ======================================================================


class TestKlipperAdapter:
    CFG = {"moonraker_url": "http://192.168.1.10:7125"}

    def _make(self):
        from adapters.printer.klipper_moonraker import KlipperAdapter
        return KlipperAdapter(self.CFG)

    def test_check_status_ok(self):
        adapter = self._make()
        with patch("adapters.printer.klipper_moonraker.requests") as mock_req:
            mock_req.get.return_value = MagicMock(status_code=200)
            assert adapter.check_status() is True
            mock_req.get.assert_called_once_with(
                "http://192.168.1.10:7125/printer/objects/query?print_stats",
                timeout=5,
            )

    def test_check_status_unreachable(self):
        adapter = self._make()
        with patch("adapters.printer.klipper_moonraker.requests") as mock_req:
            mock_req.get.return_value = MagicMock(status_code=503)
            assert adapter.check_status() is False

    def test_pause_sends_post(self):
        adapter = self._make()
        with patch("adapters.printer.klipper_moonraker.requests") as mock_req:
            mock_req.post.return_value = MagicMock(status_code=200)
            adapter.pause()
            mock_req.post.assert_called_once_with(
                "http://192.168.1.10:7125/printer/print/pause", timeout=10,
            )

    def test_stop_sends_cancel(self):
        adapter = self._make()
        with patch("adapters.printer.klipper_moonraker.requests") as mock_req:
            mock_req.post.return_value = MagicMock(status_code=200)
            adapter.stop()
            mock_req.post.assert_called_once_with(
                "http://192.168.1.10:7125/printer/print/cancel", timeout=10,
            )

    def test_resume_sends_post(self):
        adapter = self._make()
        with patch("adapters.printer.klipper_moonraker.requests") as mock_req:
            mock_req.post.return_value = MagicMock(status_code=200)
            adapter.resume()
            mock_req.post.assert_called_once_with(
                "http://192.168.1.10:7125/printer/print/resume", timeout=10,
            )

    def test_url_resolution_with_host_only(self):
        from adapters.printer.klipper_moonraker import KlipperAdapter
        adapter = KlipperAdapter({"host": "10.0.0.5"})
        assert adapter._base == "http://10.0.0.5"


# ======================================================================
# PrusaAdapter (HTTP via requests, multi-endpoint fallback)
# ======================================================================


class TestPrusaAdapter:
    CFG = {
        "url": "http://192.168.1.20",
        "username": "user",
        "password": "pass",
        "api_key": "test-key",
    }

    def _make(self):
        from adapters.printer.prusa_link import PrusaAdapter
        return PrusaAdapter(self.CFG)

    def test_check_status_ok(self):
        adapter = self._make()
        with patch("adapters.printer.prusa_link.requests") as mock_req:
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {"state": "printing"}
            mock_req.request.return_value = mock_resp
            assert adapter.check_status() is True

    def test_check_status_fails(self):
        adapter = self._make()
        with patch("adapters.printer.prusa_link.requests") as mock_req:
            mock_req.request.return_value = MagicMock(status_code=500)
            assert adapter.check_status() is False

    def test_pause_first_endpoint_succeeds(self):
        adapter = self._make()
        with patch("adapters.printer.prusa_link.requests") as mock_req:
            mock_resp_ok = MagicMock(status_code=200)
            mock_resp_ok.json.return_value = {"state": "printing"}
            mock_req.request.return_value = mock_resp_ok
            adapter.pause()
            # First call is _fetch_status_json (GET), then the actual pause POST
            post_calls = [
                c for c in mock_req.request.call_args_list
                if c[0][0] == "POST"
            ]
            assert len(post_calls) >= 1
            assert "/api/job" in post_calls[0][0][1]

    def test_stop_first_endpoint_succeeds(self):
        adapter = self._make()
        with patch("adapters.printer.prusa_link.requests") as mock_req:
            mock_resp_ok = MagicMock(status_code=200)
            mock_resp_ok.json.return_value = {"state": "printing"}
            mock_req.request.return_value = mock_resp_ok
            adapter.stop()
            post_calls = [
                c for c in mock_req.request.call_args_list
                if c[0][0] == "POST"
            ]
            assert len(post_calls) >= 1
            assert "/api/job" in post_calls[0][0][1]

    def test_resume_first_endpoint_succeeds(self):
        adapter = self._make()
        with patch("adapters.printer.prusa_link.requests") as mock_req:
            mock_req.request.return_value = MagicMock(status_code=200)
            adapter.resume()
            first_call = mock_req.request.call_args_list[0]
            assert first_call[0][0] == "POST"
            assert "/api/job" in first_call[0][1]

    def test_api_key_sent_as_header(self):
        adapter = self._make()
        with patch("adapters.printer.prusa_link.requests") as mock_req:
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {"state": "printing"}
            mock_req.request.return_value = mock_resp
            adapter.check_status()
            headers = mock_req.request.call_args[1].get("headers", {})
            assert headers.get("X-Api-Key") == "test-key"


# ======================================================================
# UltimakerAdapter (HTTP via requests, Digest auth)
# ======================================================================


class TestUltimakerAdapter:
    CFG = {
        "host": "192.168.1.30",
        "username": "admin",
        "password": "secret",
        "pairing_id": "pair123",
    }

    def _make(self):
        from adapters.printer.ultimaker_rest import UltimakerAdapter
        return UltimakerAdapter(self.CFG)

    def test_check_status_ok(self):
        adapter = self._make()
        with patch("adapters.printer.ultimaker_rest.requests") as mock_req:
            mock_req.get.return_value = MagicMock(status_code=200)
            assert adapter.check_status() is True
            mock_req.get.assert_called_once_with(
                "http://192.168.1.30/api/v1/print_job/state", timeout=5,
            )

    def test_check_status_unreachable(self):
        adapter = self._make()
        with patch("adapters.printer.ultimaker_rest.requests") as mock_req:
            mock_req.get.return_value = MagicMock(status_code=503)
            assert adapter.check_status() is False

    def test_pause_sends_put(self):
        adapter = self._make()
        with patch("adapters.printer.ultimaker_rest.requests") as mock_req:
            mock_req.request.return_value = MagicMock(status_code=200)
            adapter.pause()
            mock_req.request.assert_called_once()
            args, kwargs = mock_req.request.call_args
            assert args[0] == "PUT"
            assert "print_job/state" in args[1]
            assert kwargs["json"] == {"target": "pause"}

    def test_stop_sends_abort(self):
        adapter = self._make()
        with patch("adapters.printer.ultimaker_rest.requests") as mock_req:
            mock_req.request.return_value = MagicMock(status_code=200)
            adapter.stop()
            mock_req.request.assert_called_once()
            _, kwargs = mock_req.request.call_args
            assert kwargs["json"] == {"target": "abort"}

    def test_resume_sends_print(self):
        adapter = self._make()
        with patch("adapters.printer.ultimaker_rest.requests") as mock_req:
            mock_req.request.return_value = MagicMock(status_code=200)
            adapter.resume()
            mock_req.request.assert_called_once()
            _, kwargs = mock_req.request.call_args
            assert kwargs["json"] == {"target": "print"}

    def test_auth_fallback_on_403(self):
        adapter = self._make()
        resp_403 = MagicMock(status_code=403)
        resp_200 = MagicMock(status_code=200)
        with patch("adapters.printer.ultimaker_rest.requests") as mock_req:
            mock_req.request.side_effect = [resp_403, resp_200]
            adapter.pause()
            assert mock_req.request.call_count == 2


# ======================================================================
# BambulabAdapter (MQTT via paho.mqtt.client)
# ======================================================================


class TestBambulabAdapter:
    CFG = {
        "host": "192.168.1.40",
        "access_code": "12345678",
        "serial": "SERIAL001",
    }

    def _make(self):
        from adapters.printer.bambu_mqtt import BambulabAdapter
        return BambulabAdapter(self.CFG)

    def test_topics_derived_from_serial(self):
        adapter = self._make()
        assert adapter._request_topic == "device/SERIAL001/request"
        assert adapter._report_topic == "device/SERIAL001/report"

    def test_check_status_connected(self):
        adapter = self._make()

        mock_client = MagicMock()
        # Simulate successful connect and message receipt
        def fake_connect(host, port, keepalive):
            # Fire on_connect callback
            mock_client.on_connect(mock_client, None, None, 0)

        def fake_subscribe(topic):
            # Fire on_message after subscribe with a report
            msg = MagicMock()
            msg.payload = json.dumps({"print": {"gcode_state": "RUNNING"}}).encode()
            mock_client.on_message(mock_client, None, msg)

        mock_client.connect.side_effect = fake_connect
        mock_client.subscribe.side_effect = fake_subscribe

        with patch("paho.mqtt.client.Client", return_value=mock_client):
            from adapters.printer.bambu_mqtt import BambulabAdapter
            fresh = BambulabAdapter(self.CFG)
            result = fresh.check_status()
            assert result is True
            mock_client.username_pw_set.assert_called_once_with("bblp", "12345678")

    def test_check_status_timeout(self):
        adapter = self._make()

        mock_client = MagicMock()
        # Simulate connection timeout — on_connect never fires with rc=0
        mock_client.connect.return_value = None

        with patch("paho.mqtt.client.Client", return_value=mock_client):
            from adapters.printer.bambu_mqtt import BambulabAdapter
            fresh = BambulabAdapter(self.CFG)
            result = fresh.check_status()
            assert result is False

    def test_pause_publishes_command(self):
        mock_client = MagicMock()
        published_messages = []

        def capture_publish(topic, payload):
            published_messages.append((topic, json.loads(payload)))
            # After the pause command is published, simulate PAUSED report
            data = json.loads(payload)
            if isinstance(data.get("print"), dict) and data["print"].get("command") == "pause":
                msg = MagicMock()
                msg.payload = json.dumps({"print": {"gcode_state": "PAUSED"}}).encode()
                mock_client.on_message(mock_client, None, msg)

        mock_client.publish.side_effect = capture_publish

        def fake_connect(host, port, keepalive):
            mock_client.on_connect(mock_client, None, None, 0)

        mock_client.connect.side_effect = fake_connect

        def fake_subscribe(topic):
            # Initial state report: RUNNING (not paused)
            msg = MagicMock()
            msg.payload = json.dumps({"print": {"gcode_state": "RUNNING"}}).encode()
            mock_client.on_message(mock_client, None, msg)

        mock_client.subscribe.side_effect = fake_subscribe

        with patch("paho.mqtt.client.Client", return_value=mock_client):
            from adapters.printer.bambu_mqtt import BambulabAdapter
            fresh = BambulabAdapter(self.CFG)
            fresh.pause()

        pause_cmds = [
            (t, p) for t, p in published_messages
            if isinstance(p.get("print"), dict) and p["print"].get("command") == "pause"
        ]
        assert len(pause_cmds) >= 1
        assert pause_cmds[0][0] == "device/SERIAL001/request"
