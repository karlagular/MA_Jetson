"""
Pytest configuration for hardware-in-the-loop (HIL) tests.

HIL tests require real hardware (cameras, printers) and are typically slow and
environment-dependent. They are separated from integration tests because:
  1. They cannot run in most CI/CD pipelines without special hardware
  2. They require external dependencies (network, physical devices)
  3. They may have non-deterministic timing

Markers available:
  @pytest.mark.hil_camera       - Tests involving real camera hardware
  @pytest.mark.hil_printer      - Tests involving real printer hardware
  @pytest.mark.hil_full_system  - Full system tests involving multiple components

Run HIL tests:
    pytest tests/integration/hil/
    pytest tests/integration/hil/ -v
    pytest tests/integration/hil/ -m hil_printer   # only printer tests
    pytest tests/integration/hil/ -m "not hil_camera"  # skip camera tests

Skip HIL tests (recommended for CI):
    pytest tests/ --ignore=tests/integration/hil/
    pytest tests/integration/ --ignore=tests/integration/hil/
"""

from __future__ import annotations

import pytest


def pytest_configure(config):
    """Register HIL markers."""
    config.addinivalue_line("markers", "hil_camera: marks tests as requiring real camera hardware")
    config.addinivalue_line("markers", "hil_printer: marks tests as requiring real printer hardware")
    config.addinivalue_line("markers", "hil_full_system: marks tests as requiring full system integration")
