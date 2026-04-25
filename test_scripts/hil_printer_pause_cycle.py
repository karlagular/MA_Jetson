#!/usr/bin/env python3
"""Manual HIL script: printer control cycle on real hardware."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_machine_config
from adapters.printer.bambu_mqtt import BambulabAdapter
from adapters.printer.klipper_moonraker import KlipperAdapter
from adapters.printer.prusa_link import PrusaAdapter
from adapters.printer.ultimaker_rest import UltimakerAdapter


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Manual HIL: printer pause/resume/stop cycle",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--printer",
        choices=["Bambulab", "Prusa", "Ultimaker", "RatRig"],
        required=True,
        help="Select which real printer adapter to test in this HIL run.",
    )
    p.add_argument(
        "--sequence",
        choices=["pause-resume", "pause-stop"],
        default="pause-resume",
        help="Choose the command sequence: temporary interruption (pause-resume) or controlled cancel (pause-stop).",
    )
    p.add_argument(
        "--machine-config",
        default="machine_config.json",
        help="Path to machine configuration JSON containing printer endpoints and credentials.",
    )
    p.add_argument(
        "--skip-connectivity-check",
        action="store_true",
        help="Skip initial printer reachability/status check. Useful only if connectivity was verified just before.",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm safety prompts (non-interactive mode). Use carefully on real hardware.",
    )
    return p.parse_args()


def _make_printer(printer_name: str, machine_cfg: dict):
    cfg = machine_cfg.get(printer_name)
    if cfg is None:
        raise ValueError(f"No config found for printer '{printer_name}'")

    if printer_name == "Bambulab":
        return BambulabAdapter(cfg)
    if printer_name == "Prusa":
        return PrusaAdapter(cfg)
    if printer_name == "Ultimaker":
        return UltimakerAdapter(cfg)
    if printer_name == "RatRig":
        return KlipperAdapter(cfg)

    raise ValueError(f"Unsupported printer '{printer_name}'")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _timed_call(name: str, fn) -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    try:
        fn()
        dt = (time.perf_counter() - t0) * 1000.0
        return True, dt, "ok"
    except Exception as exc:
        dt = (time.perf_counter() - t0) * 1000.0
        return False, dt, str(exc)


def main() -> int:
    args = _parse_args()
    machine_cfg = load_machine_config(args.machine_config)
    printer = _make_printer(args.printer, machine_cfg)

    print(f"[HIL] Target printer: {args.printer}")
    print(f"[HIL] Sequence      : {args.sequence}")

    if not args.skip_connectivity_check:
        print("[HIL] Running connectivity check...")
        try:
            connected = printer.check_status()
        except Exception as exc:
            print(f"[HIL][ERROR] Connectivity check failed with exception: {exc}")
            return 1
        if not connected:
            print("[HIL][ERROR] Printer not reachable")
            return 1
        print("[HIL] Connectivity check: OK")

    if not _confirm("Confirm an active print job exists and can be controlled safely", args.yes):
        print("[HIL] Aborted by user")
        return 2

    results: list[tuple[str, bool, float, str]] = []

    ok, dt_ms, msg = _timed_call("pause", printer.pause)
    results.append(("pause", ok, dt_ms, msg))
    print(f"[HIL] pause  -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    if not ok:
        print("[HIL][ERROR] Sequence aborted after pause failure")
        return 1

    time.sleep(1.0)

    if args.sequence == "pause-resume":
        ok, dt_ms, msg = _timed_call("resume", printer.resume)
        results.append(("resume", ok, dt_ms, msg))
        print(f"[HIL] resume -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")
    else:
        if not _confirm("About to STOP/CANCEL the job. Continue", args.yes):
            print("[HIL] Stop step skipped by user")
            results.append(("stop", False, 0.0, "skipped_by_user"))
        else:
            ok, dt_ms, msg = _timed_call("stop", printer.stop)
            results.append(("stop", ok, dt_ms, msg))
            print(f"[HIL] stop   -> {'OK' if ok else 'FAIL'} ({dt_ms:.1f} ms) {msg}")

    print("\n[HIL][SUMMARY] Printer cycle")
    for step, ok, dt_ms, msg in results:
        print(f"  {step:6s} status={'OK' if ok else 'FAIL'} duration_ms={dt_ms:.1f} detail={msg}")

    all_ok = all(item[1] for item in results)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
