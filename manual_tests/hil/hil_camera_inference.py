#!/usr/bin/env python3
"""Manual HIL script: real camera + real YOLO inference with console report."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.camera.basler_pypylon import BaslerPylonCamera
from adapters.camera.opencv_usb import OpenCVUSBCamera
from adapters.camera.rtsp_gstreamer import RTSPGStreamerCamera
from adapters.inference.ultralytics_yolo import UltralyticsYOLO
from pipeline.steps import draw_overlay


def _build_rtsp_pipeline(rtsp_url: str) -> str:
    # RTSP test pipeline is created here. This GStreamer string defines how
    # frames are pulled and decoded for the RTSP camera path in this HIL script.
    return (
        f"rtspsrc location={rtsp_url} latency=200 ! "
        "rtph264depay ! h264parse ! nvv4l2decoder ! "
        "nvvidconv ! video/x-raw,format=BGRx ! "
        "videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Manual HIL: camera -> inference",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--camera",
        choices=["basler", "usb", "rtsp"],
        default="usb",
        help="Select which real camera backend to test: basler (pypylon), usb (OpenCV), or rtsp (GStreamer pipeline).",
    )
    p.add_argument(
        "--model-path",
        default="yolo11n-seg.pt",
        help="Path to the YOLO model file used for inference during this HIL run.",
    )
    p.add_argument(
        "--conf",
        type=float,
        default=0.5,
        help="YOLO confidence threshold. Higher values reduce false positives but may miss weak detections.",
    )
    p.add_argument(
        "--max-frames",
        type=int,
        default=300,
        help="Maximum number of frames to process before the script stops automatically.",
    )
    p.add_argument(
        "--warmup-frames",
        type=int,
        default=5,
        help="Number of initial frames excluded from latency stats to avoid startup bias.",
    )
    p.add_argument(
        "--display",
        action="store_true",
        help="Show live overlay window with detections. Press 'q' to stop early.",
    )
    p.add_argument(
        "--report-json",
        default="",
        help="Optional output file for a machine-readable run summary (JSON). Leave empty to disable report file writing.",
    )
    p.add_argument(
        "--basler-serial",
        default=None,
        help="Optional Basler serial number. If omitted, the first detected Basler camera is used.",
    )
    p.add_argument(
        "--usb-device",
        type=int,
        default=0,
        help="OpenCV USB camera device index (for example 0 for /dev/video0, 1 for /dev/video1).",
    )
    p.add_argument(
        "--usb-width",
        type=int,
        default=640,
        help="Requested frame width for USB camera capture.",
    )
    p.add_argument(
        "--usb-height",
        type=int,
        default=480,
        help="Requested frame height for USB camera capture.",
    )
    p.add_argument(
        "--rtsp-url",
        default="rtsp://192.168.178.68:8554/cam",
        help="RTSP stream URL used when --camera rtsp is selected.",
    )
    return p.parse_args()


def _make_camera(args: argparse.Namespace):
    if args.camera == "basler":
        return BaslerPylonCamera(serial=args.basler_serial)
    if args.camera == "rtsp":
        # The pipeline created above is consumed here and injected into
        # RTSPGStreamerCamera for the actual test run.
        return RTSPGStreamerCamera(_build_rtsp_pipeline(args.rtsp_url))
    return OpenCVUSBCamera(
        device_id=args.usb_device,
        width=args.usb_width,
        height=args.usb_height,
    )


def _summary_dict(args: argparse.Namespace, latencies_ms: list[float], person_frames: int, total_frames: int) -> dict[str, Any]:
    return {
        "script": "hil_camera_inference",
        "camera": args.camera,
        "model_path": args.model_path,
        "conf": args.conf,
        "total_frames": total_frames,
        "person_frames": person_frames,
        "person_frame_ratio": (person_frames / total_frames) if total_frames else 0.0,
        "latency_ms_avg": mean(latencies_ms) if latencies_ms else 0.0,
        "latency_ms_min": min(latencies_ms) if latencies_ms else 0.0,
        "latency_ms_max": max(latencies_ms) if latencies_ms else 0.0,
    }


def main() -> int:
    args = _parse_args()

    camera = _make_camera(args)
    model = UltralyticsYOLO(args.model_path, conf=args.conf)

    if not camera.open():
        print("[HIL][ERROR] Camera open failed")
        return 1

    frame_idx = 0
    person_frames = 0
    latencies_ms: list[float] = []
    wall_start = time.perf_counter()

    colors = [[0, 255, 0], [0, 180, 255], [255, 200, 0], [255, 0, 0]]

    print("[HIL] Camera stream opened. Running inference...")
    try:
        while frame_idx < args.max_frames:
            ok, frame = camera.read_frame()
            if not ok or frame is None:
                print("[HIL][WARN] read_frame failed or stream ended")
                break

            t0 = time.perf_counter()
            result = model.predict(frame)
            dt_ms = (time.perf_counter() - t0) * 1000.0

            if frame_idx >= args.warmup_frames:
                latencies_ms.append(dt_ms)

            if result.person_count > 0:
                person_frames += 1

            if frame_idx == 0 or frame_idx % 25 == 0:
                print(
                    f"[HIL] frame={frame_idx:04d} persons={result.person_count} "
                    f"boxes={len(result.boxes)} infer_ms={dt_ms:.2f}"
                )

            if args.display:
                overlay = draw_overlay(frame, result, colors)
                cv2.putText(
                    overlay,
                    f"frame={frame_idx} persons={result.person_count} infer={dt_ms:.1f}ms",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                )
                cv2.imshow("HIL Camera->Inference", overlay)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("[HIL] User requested stop via keyboard")
                    break

            frame_idx += 1
    finally:
        camera.close()
        if args.display:
            cv2.destroyAllWindows()

    wall_s = max(time.perf_counter() - wall_start, 1e-9)
    fps = frame_idx / wall_s

    summary = _summary_dict(args, latencies_ms, person_frames, frame_idx)
    summary["effective_fps"] = fps

    print("\n[HIL][SUMMARY] Camera->Inference")
    print(f"  frames_total      : {frame_idx}")
    print(f"  person_frames     : {person_frames}")
    print(f"  effective_fps     : {fps:.2f}")
    print(f"  infer_ms_avg      : {summary['latency_ms_avg']:.2f}")
    print(f"  infer_ms_min/max  : {summary['latency_ms_min']:.2f}/{summary['latency_ms_max']:.2f}")

    if args.report_json:
        with open(args.report_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"[HIL] Wrote JSON report to {args.report_json}")

    return 0 if frame_idx > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
