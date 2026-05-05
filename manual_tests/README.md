# Manual Tests

**Status:** ⚠️ Superseded by `tests_hil_integration/` (pytest-based)

This folder contains legacy standalone test scripts for manual testing and debugging. These scripts are **still functional and usable** but are no longer the recommended approach for new work.

## Structure

```
manual_tests/
├── README.md                          # This file
├── hil/                               # Legacy HIL test scripts
│   ├── hil_camera_inference.py        # Real camera + YOLO (standalone)
│   ├── hil_printer_pause_cycle.py     # Printer pause/resume/stop (standalone)
│   └── hil_runtime_printer_flow.py    # Full system + real printer (standalone)
│
├── prusalink_*.py                     # Individual Prusa Link adapter tests
├── ultimaker_*.py                     # Individual Ultimaker adapter tests
├── bambulab_*.py                      # Individual Bambu Lab adapter tests
├── basler_test.py                     # Individual Basler camera test
└── ratos_pause_test.py                # Individual RatRig adapter test
```

## Migrated Tests

The three main HIL tests have been migrated to pytest format in `tests_hil_integration/`:

| Script | New Location | Status | Recommendation |
|--------|---|---|---|
| `hil/hil_camera_inference.py` | `tests_hil_integration/test_camera_inference.py` | ✅ Migrated | Use pytest version |
| `hil/hil_printer_pause_cycle.py` | `tests_hil_integration/test_printer_pause_cycle.py` | ✅ Migrated | Use pytest version |
| `hil/hil_runtime_printer_flow.py` | `tests_hil_integration/test_runtime_printer_flow.py` | ✅ Migrated | Use pytest version |

## Running Manual Tests

### HIL test scripts (standalone Python)
```bash
python manual_tests/hil/hil_camera_inference.py --camera=usb --max-frames=50
python manual_tests/hil/hil_printer_pause_cycle.py --printer=Prusa --sequence=pause-resume
python manual_tests/hil/hil_runtime_printer_flow.py --printer=Bambulab --auto-user-action=continue
```

### Individual adapter tests (standalone Python)
```bash
python manual_tests/prusalink_status_test.py
python manual_tests/ultimaker_pause_test.py
python manual_tests/bambulab_status_test.py
```

### Ultimaker direct-Ethernet prerequisites

Before running `ultimaker_*.py` scripts over a direct Ethernet cable:

1. Run pairing once to create/store API credentials:

```bash
python manual_tests/ultimaker_pair_once.py
```

2. Ensure Jetson networking matches the Ultimaker subnet. For link-local setups (for example `169.254.x.x`), set a temporary IP/route on `eth0` so traffic goes to the cable interface.
3. Verify connectivity first:

```bash
ping -I eth0 -c 2 <ultimaker_ip>
curl --interface eth0 -i http://<ultimaker_ip>/api/v1/printer
```

See the Ultimaker setup section in the top-level README for the exact temporary `ip addr` / `ip route` commands and IPv4 format checks.

### Bambu Lab X1E IP note

For Bambu Lab X1E setups, the printer IP address can be set manually directly on the printer. Use this when you need the printer IP/subnet to match the Jetson network.

## Recommended Use

### For new work: Use pytest format (tests_hil_integration/)
```bash
# Pytest format is recommended
pytest tests_hil_integration/test_printer_pause_cycle.py --printer=Prusa -v
pytest tests_hil_integration/test_camera_inference.py --camera=usb -v
```

### For quick manual testing: Use standalone scripts (this folder)
```bash
# Direct Python execution
python manual_tests/hil/hil_printer_pause_cycle.py --printer=Prusa
python manual_tests/prusalink_pause_test.py
```

## Why These Are Superseded

**pytest-based tests** (`tests_hil_integration/`) offer:
- ✅ CI/CD integration
- ✅ Pytest markers for selective execution
- ✅ Standard output format
- ✅ Better IDE support
- ✅ Easier parameterization
- ✅ Integrated with main test suite

**Standalone scripts** (this folder):
- ⚠️ No CI/CD integration
- ⚠️ No markers/selective execution
- ⚠️ Custom output format
- ⚠️ Slower feedback loop
- ✅ Still useful for quick manual testing

## Migration Path

If you need to convert individual manual test scripts:
1. Use `tests_hil_integration/test_printer_pause_cycle.py` as a template
2. Create pytest test functions for each adapter combination
3. Use pytest markers for filtering
4. Submit as tests in `tests_hil_integration/`

## Future Cleanup

After confirming all needed tests work in pytest format, this folder can be:
- **Archived** for historical reference
- **Deleted** if no longer needed
- **Selectively kept** only for scripts you regularly run manually

## See Also

- Pytest-based HIL tests: `tests_hil_integration/README.md`
- Main test suite: `tests/README.md`
- Project documentation
