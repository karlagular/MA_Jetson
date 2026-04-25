# Manual HIL Test Scripts

**Status:** ⚠️ Legacy standalone scripts (superseded by pytest version in `tests_hil_integration/`)

This subfolder contains the three main hardware-in-the-loop (HIL) test scripts in their original standalone format. These scripts are still fully functional but have been migrated to pytest format for better CI/CD integration.

## Available Scripts

### `hil_camera_inference.py`
Tests real camera capture + YOLO inference pipeline.

```bash
python hil_camera_inference.py \
  --camera=usb \
  --model-path=yolo11n-seg.pt \
  --max-frames=100 \
  --display
```

**Options:**
- `--camera`: `usb`, `basler`, `rtsp` (default: usb)
- `--model-path`: Path to YOLO model file
- `--max-frames`: Max frames to capture
- `--display`: Show live overlay window
- `--usb-device`, `--usb-width`, `--usb-height`: USB camera settings
- `--basler-serial`: Basler camera serial number
- `--rtsp-url`: RTSP stream URL

### `hil_printer_pause_cycle.py`
Tests pause → resume or pause → stop on real printer.

```bash
python hil_printer_pause_cycle.py \
  --printer=Prusa \
  --sequence=pause-resume \
  --machine-config=machine_config.json
```

**Options:**
- `--printer`: `Bambulab`, `Prusa`, `Ultimaker`, `RatRig` (required)
- `--sequence`: `pause-resume` or `pause-stop` (default: pause-resume)
- `--machine-config`: Path to machine config JSON
- `--skip-connectivity-check`: Skip initial printer check
- `--yes`: Auto-confirm safety prompts

### `hil_runtime_printer_flow.py`
Tests full orchestrator + runtime + real printer integration.

```bash
python hil_runtime_printer_flow.py \
  --printer=Bambulab \
  --auto-user-action=continue \
  --machine-config=machine_config.json
```

**Options:**
- `--printer`: `Bambulab`, `Prusa`, `Ultimaker`, `RatRig` (required)
- `--machine-config`: Path to machine config JSON
- `--auto-user-action`: `continue`, `stop`, `manual` (default: manual)
- `--timeout-s`: Timeout per state transition
- `--skip-connectivity-check`: Skip initial printer check

## Recommended Migration Path

For new work, use the pytest-based versions instead:

```bash
# Instead of:
python manual_tests/hil/hil_printer_pause_cycle.py --printer=Prusa

# Use:
pytest tests_hil_integration/test_printer_pause_cycle.py --printer=Prusa -v
```

**Benefits of pytest version:**
- ✅ Runs in CI/CD pipelines
- ✅ Pytest markers for filtering
- ✅ Integrated with main test suite
- ✅ Better output formatting
- ✅ Can run multiple tests in sequence

## When to Use These

Use these standalone scripts for:
- **Quick manual testing** when you prefer direct Python execution
- **Debugging** without pytest overhead
- **Historical reference** or documentation
- **Isolated testing** on hardware without CI/CD

## See Also

- Pytest-based HIL tests: `../../../tests_hil_integration/`
- Parent README: `../README.md`
- Project documentation
