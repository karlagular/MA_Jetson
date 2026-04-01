import requests

from legacy.printer_control.ports import PrinterPort


class KlipperAdapter(PrinterPort):
    """Adapter for RatRig printers running Klipper/Moonraker."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._base = self._resolve_base_url(cfg)

    @staticmethod
    def _resolve_base_url(cfg: dict) -> str:
        base = cfg.get("moonraker_url") or cfg.get("url") or cfg.get("host")
        if not base:
            raise ValueError("RatRig config requires 'moonraker_url' (or 'url'/'host')")
        if not str(base).startswith(("http://", "https://")):
            base = "http://" + str(base)
        return str(base).rstrip("/")

    def check_status(self) -> bool:
        r = requests.get(f"{self._base}/printer/objects/query?print_stats", timeout=5)
        return 200 <= r.status_code < 300

    def pause(self) -> None:
        url = f"{self._base}/printer/print/pause"
        r = requests.post(url, timeout=10)
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] RatRig(Klipper) pause: HTTP {r.status_code}")
            return
        print(f"[PrinterControl] RatRig(Klipper) pause failed: HTTP {r.status_code}")

    def stop(self) -> None:
        url = f"{self._base}/printer/print/cancel"
        r = requests.post(url, timeout=10)
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] RatRig(Klipper) cancel: HTTP {r.status_code}")
            return
        print(f"[PrinterControl] RatRig(Klipper) cancel failed: HTTP {r.status_code}")

    def resume(self) -> None:
        url = f"{self._base}/printer/print/resume"
        r = requests.post(url, timeout=10)
        if 200 <= r.status_code < 300:
            print(f"[PrinterControl] RatRig(Klipper) resume: HTTP {r.status_code}")
            return
        print(f"[PrinterControl] RatRig(Klipper) resume failed: HTTP {r.status_code}")
