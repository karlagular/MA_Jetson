#!/usr/bin/env python3
import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone Basler USB camera test for Jetson (pypylon)."
    )
    parser.add_argument(
        "--serial",
        type=str,
        default=None,
        help="Optional Basler camera serial number. Uses first detected camera if omitted.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Stop after N frames. Use 0 for unlimited.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=3000,
        help="Frame grab timeout in milliseconds.",
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="Show live preview via OpenCV window.",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default=None,
        help="Optional directory for periodic frame snapshots.",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=0,
        help="Save every Nth frame when --save-dir is set. 0 disables saving.",
    )
    return parser.parse_args()


def pick_device(factory, serial: str | None):
    devices = factory.EnumerateDevices()
    if not devices:
        return None, []

    if serial is None:
        return devices[0], devices

    for dev in devices:
        if dev.GetSerialNumber() == serial:
            return dev, devices

    return None, devices


def basler_visible_in_lsusb() -> bool:
    try:
        out = subprocess.check_output(["lsusb"], text=True, stderr=subprocess.STDOUT)
    except Exception:
        return False
    return "Basler" in out or "2676:" in out


def main() -> int:
    args = parse_args()

    try:
        from pypylon import pylon
    except ImportError:
        print("ERROR: pypylon is not installed. Install with: python3 -m pip install pypylon")
        return 1

    cv2 = None
    if args.display or args.save_dir:
        try:
            import cv2  # type: ignore
        except ImportError:
            if args.display:
                print("ERROR: OpenCV is required for --display.")
                return 1
            print("WARNING: OpenCV not installed. Disabling frame saving.")
            args.save_dir = None

    factory = pylon.TlFactory.GetInstance()
    selected_device, devices = pick_device(factory, args.serial)

    if not devices:
        print("ERROR: No Basler camera detected.")
        print("Check USB cable/port, power, and run: lsusb")
        if basler_visible_in_lsusb():
            print("Detected Basler in lsusb, but pypylon cannot access it.")
            print("Likely a udev permission issue on /dev/bus/usb.")
            print("Fix (run once with sudo):")
            print("  echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"2676\", GROUP=\"plugdev\", MODE=\"0660\"' | sudo tee /etc/udev/rules.d/99-basler-usb.rules")
            print("  sudo udevadm control --reload-rules")
            print("  sudo udevadm trigger")
            print("Then unplug/replug the camera and retry.")
        return 1

    print(f"Detected {len(devices)} camera(s):")
    for idx, dev in enumerate(devices, start=1):
        print(
            f"  {idx}. model={dev.GetModelName()} serial={dev.GetSerialNumber()} transport={dev.GetDeviceClass()}"
        )

    if selected_device is None:
        print(f"ERROR: Requested serial '{args.serial}' not found.")
        return 1

    camera = pylon.InstantCamera(factory.CreateDevice(selected_device))
    camera.Open()

    print(
        f"Using model={camera.GetDeviceInfo().GetModelName()} serial={camera.GetDeviceInfo().GetSerialNumber()}"
    )

    converter = pylon.ImageFormatConverter()
    converter.OutputPixelFormat = pylon.PixelType_BGR8packed
    converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

    save_dir = Path(args.save_dir) if args.save_dir else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    keep_running = True

    def _stop_handler(signum, frame):
        del signum, frame
        nonlocal keep_running
        keep_running = False

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    frame_count = 0
    start_time = time.time()

    if args.display and cv2 is not None:
        cv2.namedWindow("Basler Preview", cv2.WINDOW_AUTOSIZE)

    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    print("Started grabbing. Press Ctrl+C to stop.")

    try:
        while camera.IsGrabbing() and keep_running:
            grab_result = camera.RetrieveResult(args.timeout_ms, pylon.TimeoutHandling_ThrowException)

            if not grab_result.GrabSucceeded():
                print(f"WARNING: Grab failed with error {grab_result.GetErrorCode()}: {grab_result.GetErrorDescription()}")
                grab_result.Release()
                continue

            image = converter.Convert(grab_result)
            frame = image.GetArray()
            frame_count += 1

            elapsed = time.time() - start_time
            if elapsed > 0:
                fps = frame_count / elapsed
            else:
                fps = 0.0

            if frame_count == 1 or frame_count % 30 == 0:
                h, w = frame.shape[:2]
                print(f"Frame {frame_count}: {w}x{h}, avg_fps={fps:.2f}")

            if save_dir and args.save_every > 0 and frame_count % args.save_every == 0 and cv2 is not None:
                out_path = save_dir / f"frame_{frame_count:06d}.jpg"
                cv2.imwrite(str(out_path), frame)

            if args.display and cv2 is not None:
                cv2.imshow("Basler Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("Quit requested from preview window.")
                    break
                if cv2.getWindowProperty("Basler Preview", cv2.WND_PROP_AUTOSIZE) < 0:
                    print("Preview window closed.")
                    break

            grab_result.Release()

            if args.max_frames > 0 and frame_count >= args.max_frames:
                break

    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        if camera.IsGrabbing():
            camera.StopGrabbing()
        if camera.IsOpen():
            camera.Close()
        if args.display and cv2 is not None:
            cv2.destroyAllWindows()

    total_elapsed = max(time.time() - start_time, 1e-9)
    print(f"Completed. frames={frame_count}, avg_fps={frame_count / total_elapsed:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
