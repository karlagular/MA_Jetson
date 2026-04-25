# Hardware-in-the-Loop Tests Migration Summary

## Final Structure

After migration to pytest format and reorganization:

```
project_root/
├── tests/                                      # Main test suite
│   ├── unit/                                   # ✓ Unit tests (fast, mocked)
│   │   ├── test_policy.py
│   │   ├── test_state_machine.py
│   │   ├── test_alarm_runtime.py
│   │   ├── test_orchestrator.py
│   │   ├── test_printer_adapters.py
│   │   └── adapters/
│   │       ├── camera/
│   │       ├── logging/
│   │       └── inference/
│   │
│   └── integration/                            # ⚠ Integration tests (medium, stubs)
│       ├── conftest.py
│       └── test_pipeline_replay.py
│
├── tests_hil_integration/                      # ⛔ HIL tests (slow, real hardware)
│   ├── conftest.py                            # Pytest markers & config
│   ├── __init__.py
│   ├── README.md                              # Comprehensive guide
│   ├── test_camera_inference.py               # Real camera + YOLO
│   ├── test_printer_pause_cycle.py            # Real printer pause/resume/stop
│   └── test_runtime_printer_flow.py           # Full system orchestration
│
└── manual_tests/                              # 📦 Manual standalone scripts
    ├── README.md                              # Superseded by pytest
    ├── prusalink_*.py
    ├── ultimaker_*.py
    ├── bambulab_*.py
    └── basler_test.py
```

## What Changed

### 1. **Renamed `test_scripts/` → `manual_tests/`**
- Old standalone Python scripts still present and usable
- No longer recommended for new work
- Can be archived/deleted after pytest migration validation

### 2. **Created `tests_hil_integration/` (new top-level folder)**
- Separate from main `tests/` directory
- 3 main HIL tests converted to pytest format:
  - `test_camera_inference.py`
  - `test_printer_pause_cycle.py`
  - `test_runtime_printer_flow.py`
- Full docstrings and pytest markers
- Command-line parameterization

### 3. **Pytest Markers**
- `@pytest.mark.hil_camera` — Camera tests
- `@pytest.mark.hil_printer` — Printer tests
- `@pytest.mark.hil_full_system` — End-to-end tests

## Running Tests

### Standard workflow (no hardware)
```bash
# All main tests (fast)
pytest tests/ -v

# Skip nothing — hardware not available
pytest tests/ --ignore=tests_hil_integration/ -v
```

### With hardware (local dev)
```bash
# All HIL tests
pytest tests_hil_integration/ -v

# Specific marker
pytest tests_hil_integration/ -m hil_printer
pytest tests_hil_integration/ -m hil_camera

# Specific test with options
pytest tests_hil_integration/test_camera_inference.py \
  --camera=usb --max-frames=50 --display
```

### CI/CD

**Standard workflow (GitHub Actions):**
```yaml
# Run only main test suite (no hardware)
- name: Run tests (no hardware)
  run: pytest tests/ -v
```

**Hardware-gated workflow (self-hosted runners):**
```yaml
# Run HIL tests on hardware-enabled runners
- name: Run HIL tests
  if: runner.labels.has('hardware')
  run: pytest tests_hil_integration/ -m hil_printer -v
```

## File Mapping

| Old Location | New Location | Format | Status |
|---|---|---|---|
| `test_scripts/hil_camera_inference.py` | `tests_hil_integration/test_camera_inference.py` | pytest | ✅ Migrated |
| `test_scripts/hil_printer_pause_cycle.py` | `tests_hil_integration/test_printer_pause_cycle.py` | pytest | ✅ Migrated |
| `test_scripts/hil_runtime_printer_flow.py` | `tests_hil_integration/test_runtime_printer_flow.py` | pytest | ✅ Migrated |
| `test_scripts/prusalink_*.py` | `manual_tests/prusalink_*.py` | standalone | ⚠️ Manual |
| `test_scripts/ultimaker_*.py` | `manual_tests/ultimaker_*.py` | standalone | ⚠️ Manual |
| `test_scripts/bambulab_*.py` | `manual_tests/bambulab_*.py` | standalone | ⚠️ Manual |
| `test_scripts/basler_test.py` | `manual_tests/basler_test.py` | standalone | ⚠️ Manual |

## Key Improvements

✅ **Clear test taxonomy**
- Unit tests: `tests/unit/` (isolated, mocked, fast)
- Integration: `tests/integration/` (stubs, deterministic)
- HIL: `tests_hil_integration/` (real hardware, slow)

✅ **CI/CD friendly**
- Easy to skip hardware tests by default
- Pytest markers for selective execution
- Can run different tests on different runners

✅ **Professional structure**
- All tests use pytest (single framework)
- Comprehensive docstrings and README
- Command-line parameterization
- Fixture-based configuration

✅ **Better documentation**
- Each test file has full docstrings
- Dedicated README in `tests_hil_integration/`
- Safety recommendations and troubleshooting

✅ **Backward compatible**
- Legacy scripts still work as standalone Python files
- No breaking changes to existing workflows
- Gradual migration path

## Next Steps

1. **Test locally** with hardware to verify pytest versions work
2. **Update CI/CD** to use `tests/` by default (skip `tests_hil_integration/`)
3. **Archive or delete** `manual_tests/` after validation (optional)
4. **Document** in project README how to run different test suites

## Usage Summary

```bash
# Development: fast feedback (no hardware)
pytest tests/ -v

# Development: all tests including hardware
pytest tests/ tests_hil_integration/ -v

# CI/CD: standard workflow (no hardware)
pytest tests/ -v

# CI/CD: hardware runner (full suite)
pytest tests/ tests_hil_integration/ -v

# Selective: only printer HIL tests
pytest tests_hil_integration/ -m hil_printer --printer=Prusa

# Selective: only camera tests
pytest tests_hil_integration/ -m hil_camera --camera=usb
```

## Benefits Summary

✅ Separated hardware and non-hardware tests
✅ Professional pytest structure across all tests
✅ Easy CI/CD integration and selective execution
✅ Comprehensive documentation
✅ Backward compatible with legacy scripts
✅ Flexible command-line parameterization
✅ Clear upgrade path for future refactoring
