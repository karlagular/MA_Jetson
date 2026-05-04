# Hardware-in-the-Loop (HIL) Integration Tests

**Location:** `tests_hil_integration/` (separate from main test suite)

Tests in this directory require real hardware (cameras, 3D printers) and are typically slow and environment-dependent. They are kept separate from `tests/` because:

1. **Hardware requirement**: Cannot run in most CI/CD pipelines without access to physical devices
2. **Timing variability**: Network/hardware latency may cause flakiness
3. **Destructive operations**: Some tests (e.g., printer stop) have real-world consequences
4. **Manual intervention**: May require user prompts or supervised execution

## Test Structure

- **`test_camera_inference.py`** — Real camera capture + YOLO inference
  - Supports: Basler, OpenCV USB, GStreamer RTSP
  - Measures inference latency on real hardware
  
- **`test_printer_pause_cycle.py`** — Printer pause/resume/stop commands
  - Supports: Bambulab, Prusa Link, Ultimaker, RatRig (Klipper)
  - Tests both `pause→resume` and `pause→stop` sequences
  
- **`test_runtime_printer_flow.py`** — Full orchestrator + runtime + real printer
  - Simulates alarm trigger → pause → user action → recovery
  - Verified state machine transitions

## Running HIL Tests

### Run all HIL tests
```bash
pytest tests_hil_integration/ -v
```

### Run specific test by marker
```bash
# Only camera tests
pytest tests_hil_integration/ -m hil_camera

# Only printer tests
pytest tests_hil_integration/ -m hil_printer

# Only full-system tests
pytest tests_hil_integration/ -m hil_full_system

# Skip camera tests
pytest tests_hil_integration/ -m "not hil_camera"
```

### Run specific test file
```bash
pytest tests_hil_integration/test_camera_inference.py -v
pytest tests_hil_integration/test_printer_pause_cycle.py -v
pytest tests_hil_integration/test_runtime_printer_flow.py -v
```

## Command-Line Options

### Camera inference test
```bash
pytest tests_hil_integration/test_camera_inference.py \
  --camera=usb \
  --model-path=models_available/yolo11n-seg.pt \
  --conf=0.5 \
  --max-frames=300 \
  --warmup-frames=5 \
  --display \
  --usb-device=0 \
  --usb-width=640 \
  --usb-height=480
```

**Options:**
- `--camera`: `basler`, `usb`, `rtsp` (default: `usb`)
- `--model-path`: Path to YOLO model file
- `--conf`: YOLO confidence threshold (0–1)
- `--max-frames`: Max frames to capture before exiting
- `--warmup-frames`: Frames to exclude from latency stats (reduces startup bias)
- `--display`: Show live overlay window (press `q` to stop early)
- `--usb-device`: USB camera device ID (e.g. 0 for /dev/video0)
- `--usb-width`, `--usb-height`: Resolution for USB capture
- `--basler-serial`: Basler camera serial number (optional; auto-selects first if omitted)
- `--rtsp-url`: RTSP stream URL

### Printer pause cycle test
```bash
pytest tests_hil_integration/test_printer_pause_cycle.py \
  --printer=Prusa \
  --sequence=pause-resume \
  --machine-config=machine_config.json \
  --yes \
  --log-io
```

**Options:**
- `--printer`: `Bambulab`, `Prusa`, `Ultimaker`, `RatRig` (required)
- `--sequence`: `pause-resume`, `pause-stop`, or `pause-resume-pause-stop` (default: `pause-resume`)
- `--machine-config`: Path to credentials/endpoints JSON
- `--skip-connectivity-check`: Skip initial printer status check
- `--yes`: Auto-confirm safety prompts (non-interactive mode)
- `--log-io`: Write timestamped terminal results + printer TX/RX metadata into a TXT file
- `--log-dir`: Base directory for log output (default: `tests_hil_integration/logs`)

When `--log-io` is enabled, logs are written under:
- `tests_hil_integration/logs/<timestamp>/<test_name>.txt`

### Runtime printer flow test
```bash
pytest tests_hil_integration/test_runtime_printer_flow.py \
  --printer=Bambulab \
  --auto-user-action=continue \
  --machine-config=machine_config.json \
  --timeout-s=25.0
```

**Options:**
- `--printer`: `Bambulab`, `Prusa`, `Ultimaker`, `RatRig` (required)
- `--machine-config`: Path to credentials/endpoints JSON
- `--auto-user-action`: `continue`, `stop`, `manual` (default: `manual`)
  - `continue`: Automatically triggers resume
  - `stop`: Automatically triggers cancel
  - `manual`: Prompts user via terminal
- `--timeout-s`: Timeout per state transition (default: 25.0)
- `--skip-connectivity-check`: Skip initial printer check

## Safety Recommendations

1. **Printer tests**: Ensure an active print job is running before starting
2. **Pause-stop sequence**: This **cancels** the print; use only in test scenarios
3. **Auto-confirm mode (`--yes`)**: Use only in controlled environments
4. **Network connectivity**: Verify printer/camera network is stable before running
5. **Physical safety**: Clear the printer nozzle and bed area before running tests

## CI/CD Integration

### Standard workflow (skip HIL)
```yaml
- name: Run unit and integration tests (no hardware)
  run: pytest tests/ -v
```

### Optional: Hardware-gated workflow
Create a separate workflow file (`.github/workflows/hil-tests.yml`) for self-hosted runners with hardware:

```yaml
- name: Run HIL tests (hardware runners only)
  if: runner.labels.has('hardware')
  run: pytest tests_hil_integration/ -m hil_printer -v --printer=Prusa
```

## Troubleshooting

### Camera test fails to open
- Verify camera is connected: `ls /dev/video*`
- Check USB permissions: `sudo usermod -a -G video $USER`
- For Basler: verify pypylon is installed and camera is recognized

### Printer test times out
- Check printer is powered on and connected to network
- Verify print job is active (some printers require this)
- Check machine_config.json has correct credentials/endpoints
- Increase `--timeout-s` for slow networks

### RTSP pipeline fails
- Test with GStreamer directly: `gst-launch-1.0 "rtspsrc location=rtsp://... ! ..."`
- Verify NVIDIA codec libraries (nvv4l2decoder) on Jetson

## Additional Resources

- **Adapter implementations**: `adapters/camera/`, `adapters/printer/`
- **Orchestrator logic**: `app/orchestrator.py`, `app/alarm_runtime.py`
- **Domain policy**: `domain/policy.py`, `domain/state_machine.py`
