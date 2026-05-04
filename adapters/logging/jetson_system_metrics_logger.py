"""Background logger for Jetson system utilization metrics."""
# Frequency of logging in wiring.py: JetsonSystemMetricsLogger(interval_seconds=2.0)

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import traceback
from datetime import datetime

from ports.system_metrics_logger import SystemMetricsLoggerPort


class JetsonSystemMetricsLogger(SystemMetricsLoggerPort):
    def __init__(self, session_dir: str, interval_seconds: float = 2.0) -> None:
        self._dir = session_dir
        os.makedirs(self._dir, exist_ok=True)
        self._metrics_path = os.path.join(self._dir, "system_metrics.jsonl")
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()
        self._tegrastats_supported: bool | None = None
        self._prev_cpu_sample: list[tuple[int, int]] | None = None
        self._capabilities: dict[str, bool] | None = None

    def start(self) -> None:
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            try:
                self._capabilities = self._detect_capabilities()
            except Exception as exc:
                # Never let capability probing break the frame loop.
                self._capabilities = {}
                self._log_error("capability_check_failed", str(exc), traceback.format_exc())
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="jetson-metrics-logger", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._thread_lock:
            thread = self._thread
            self._thread = None
        if thread is None:
            return
        self._stop_event.set()
        thread.join(timeout=max(1.0, self._interval_seconds + 0.5))

    def _run(self) -> None:
        try:
            self._prev_cpu_sample = self._read_cpu_core_counters()
            self._write_record(
                {
                    "timestamp": datetime.now().isoformat(),
                    "record_type": "system_metrics_capabilities",
                    "capabilities": self._capabilities or {},
                }
            )
            while not self._stop_event.wait(self._interval_seconds):
                try:
                    metrics, errors = self._collect_metrics()
                except Exception as exc:
                    self._log_error("collect_metrics_failed", str(exc), traceback.format_exc())
                    continue

                if metrics is not None:
                    self._write_record(metrics)

                for message in errors:
                    self._log_error("metric_read_failed", message)
        except Exception as exc:
            self._log_error("metrics_thread_crash", str(exc), traceback.format_exc())

    def _collect_metrics(self) -> tuple[dict | None, list[str]]:
        caps = self._capabilities or {}
        errors: list[str] = []

        tegra: dict = {}
        if caps.get("gpu_utilization_percent") or caps.get("power_vdd_in_mw"):
            tegra = self._read_tegrastats()

        metrics: dict[str, object] = {
            "timestamp": datetime.now().isoformat(),
            "record_type": "system_metrics",
        }

        if caps.get("cpu_per_core_percent"):
            cpu_per_core_percent = self._read_cpu_core_percent()
            if cpu_per_core_percent is not None:
                metrics["cpu_per_core_percent"] = cpu_per_core_percent
            else:
                errors.append("cpu_per_core_percent unavailable for this sample")

        if caps.get("swap_used_bytes"):
            swap_used_bytes = self._read_swap_used_bytes()
            if swap_used_bytes is not None:
                metrics["swap_used_bytes"] = swap_used_bytes
            else:
                errors.append("swap_used_bytes read failed")

        if caps.get("temperature_cpu_c") or caps.get("temperature_gpu_c"):
            temps = self._read_temperatures(tegra)
            if caps.get("temperature_cpu_c"):
                if temps.get("cpu_c") is not None:
                    metrics["temperature_cpu_c"] = temps.get("cpu_c")
                else:
                    errors.append("temperature_cpu_c read failed")
            if caps.get("temperature_gpu_c"):
                if temps.get("gpu_c") is not None:
                    metrics["temperature_gpu_c"] = temps.get("gpu_c")
                else:
                    errors.append("temperature_gpu_c read failed")

        if caps.get("gpu_utilization_percent"):
            gpu = tegra.get("gpu_utilization_percent")
            if gpu is not None:
                metrics["gpu_utilization_percent"] = gpu
            else:
                errors.append("gpu_utilization_percent missing in tegrastats sample")

        if caps.get("power_vdd_in_mw"):
            power = tegra.get("power_vdd_in_mw")
            if power is not None:
                metrics["power_vdd_in_mw"] = power
            else:
                errors.append("power_vdd_in_mw missing in tegrastats sample")

        if len(metrics) == 2:
            return None, errors
        return metrics, errors

    def _read_cpu_core_percent(self) -> list[float] | None:
        current = self._read_cpu_core_counters()
        previous = self._prev_cpu_sample
        self._prev_cpu_sample = current
        if previous is None or len(previous) != len(current):
            return None

        result: list[float] = []
        for (prev_total, prev_idle), (cur_total, cur_idle) in zip(previous, current):
            total_delta = cur_total - prev_total
            idle_delta = cur_idle - prev_idle
            if total_delta <= 0:
                result.append(0.0)
                continue
            busy_delta = total_delta - idle_delta
            result.append(round((busy_delta / total_delta) * 100.0, 2))
        return result

    def _read_cpu_core_counters(self) -> list[tuple[int, int]]:
        counters: list[tuple[int, int]] = []
        with open("/proc/stat", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.startswith("cpu"):
                    continue
                fields = line.split()
                if fields[0] == "cpu":
                    continue
                values = [int(v) for v in fields[1:]]
                idle = values[3] + (values[4] if len(values) > 4 else 0)
                total = sum(values)
                counters.append((total, idle))
        return counters

    def _read_swap_used_bytes(self) -> int | None:
        swap_total_kb = None
        swap_free_kb = None
        try:
            with open("/proc/meminfo", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("SwapTotal:"):
                        swap_total_kb = int(line.split()[1])
                    elif line.startswith("SwapFree:"):
                        swap_free_kb = int(line.split()[1])
        except OSError:
            return None

        if swap_total_kb is None or swap_free_kb is None:
            return None
        return (swap_total_kb - swap_free_kb) * 1024

    def _read_temperatures(self, tegra: dict) -> dict:
        # Prefer tegrastats values when available because they are Jetson-specific.
        cpu_temp = tegra.get("temperature_cpu_c")
        gpu_temp = tegra.get("temperature_gpu_c")
        if cpu_temp is not None or gpu_temp is not None:
            return {"cpu_c": cpu_temp, "gpu_c": gpu_temp}

        cpu_candidates: list[float] = []
        gpu_candidate: float | None = None
        thermal_root = "/sys/class/thermal"

        try:
            entries = os.listdir(thermal_root)
        except OSError:
            return {"cpu_c": None, "gpu_c": None}

        for entry in entries:
            if not entry.startswith("thermal_zone"):
                continue
            zone_dir = os.path.join(thermal_root, entry)
            type_path = os.path.join(zone_dir, "type")
            temp_path = os.path.join(zone_dir, "temp")
            try:
                with open(type_path, "r", encoding="utf-8", errors="replace") as f_type:
                    zone_type = f_type.read().strip().lower()
                with open(temp_path, "r", encoding="utf-8", errors="replace") as f_temp:
                    raw = (f_temp.read() or "").strip()
                if not raw:
                    continue
                value = float(raw)
                if value > 1000.0:
                    value /= 1000.0
            except (OSError, ValueError, TypeError, UnicodeDecodeError):
                continue

            if "gpu" in zone_type and gpu_candidate is None:
                gpu_candidate = round(value, 2)
            if "cpu" in zone_type:
                cpu_candidates.append(value)

        cpu_avg = None
        if cpu_candidates:
            cpu_avg = round(sum(cpu_candidates) / len(cpu_candidates), 2)
        return {"cpu_c": cpu_avg, "gpu_c": gpu_candidate}

    def _read_tegrastats(self) -> dict:
        if self._tegrastats_supported is False:
            return {}

        out = ""
        try:
            proc = subprocess.run(
                ["tegrastats", "--interval", "1000"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        except subprocess.TimeoutExpired as exc:
            out = self._coerce_text(exc.stdout) + "\n" + self._coerce_text(exc.stderr)
        except (OSError, subprocess.SubprocessError):
            self._tegrastats_supported = False
            return {}

        if not out.strip():
            self._tegrastats_supported = False
            return {}

        self._tegrastats_supported = True
        return {
            "gpu_utilization_percent": self._extract_float(r"GR3D_FREQ\s+(\d+(?:\.\d+)?)%", out),
            "power_vdd_in_mw": self._extract_float(r"VDD_IN\s+(\d+(?:\.\d+)?)mW", out),
            "temperature_cpu_c": self._extract_float(r"cpu@([0-9]+(?:\.[0-9]+)?)C", out),
            "temperature_gpu_c": self._extract_float(r"gpu@([0-9]+(?:\.[0-9]+)?)C", out),
        }

    def _detect_capabilities(self) -> dict[str, bool]:
        caps = {
            "cpu_per_core_percent": False,
            "swap_used_bytes": False,
            "temperature_cpu_c": False,
            "temperature_gpu_c": False,
            "gpu_utilization_percent": False,
            "power_vdd_in_mw": False,
        }

        try:
            counters = self._read_cpu_core_counters()
            caps["cpu_per_core_percent"] = len(counters) > 0
        except Exception:
            caps["cpu_per_core_percent"] = False

        try:
            caps["swap_used_bytes"] = self._read_swap_used_bytes() is not None
        except Exception:
            caps["swap_used_bytes"] = False

        cpu_t, gpu_t = self._detect_thermal_capabilities()
        caps["temperature_cpu_c"] = cpu_t
        caps["temperature_gpu_c"] = gpu_t

        tegra = self._read_tegrastats()
        caps["gpu_utilization_percent"] = tegra.get("gpu_utilization_percent") is not None
        caps["power_vdd_in_mw"] = tegra.get("power_vdd_in_mw") is not None

        return caps

    def _detect_thermal_capabilities(self) -> tuple[bool, bool]:
        has_cpu = False
        has_gpu = False
        thermal_root = "/sys/class/thermal"

        try:
            entries = os.listdir(thermal_root)
        except OSError:
            return False, False

        for entry in entries:
            if not entry.startswith("thermal_zone"):
                continue
            zone_dir = os.path.join(thermal_root, entry)
            type_path = os.path.join(zone_dir, "type")
            temp_path = os.path.join(zone_dir, "temp")
            try:
                with open(type_path, "r", encoding="utf-8", errors="replace") as f_type:
                    zone_type = f_type.read().strip().lower()
                with open(temp_path, "r", encoding="utf-8", errors="replace") as f_temp:
                    raw = (f_temp.read() or "").strip()
                if not raw:
                    continue
                float(raw)
            except (OSError, ValueError, TypeError, UnicodeDecodeError):
                continue

            if "cpu" in zone_type:
                has_cpu = True
            if "gpu" in zone_type:
                has_gpu = True

        return has_cpu, has_gpu

    def _write_record(self, payload: dict) -> None:
        with open(self._metrics_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _log_error(self, code: str, message: str, detail: str | None = None) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "record_type": "system_metrics_error",
            "error_code": code,
            "message": message,
        }
        if detail:
            payload["detail"] = detail
        try:
            self._write_record(payload)
        except Exception:
            print(f"[SystemMetricsLogger] {code}: {message}")

    @staticmethod
    def _extract_float(pattern: str, text: str) -> float | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _coerce_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)
