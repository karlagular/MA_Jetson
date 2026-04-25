"""
Shared pytest configuration for the entire test suite.

Adds the project root to sys.path so that all top-level packages (domain,
adapters, app, pipeline, ports, etc.) are importable from any test file,
regardless of how deep in the tests/ directory tree the test lives.

Loaded automatically by pytest before any test is collected; no explicit
import is required.

Usage:
    pytest                          # run all tests
    pytest tests/unit/              # run only unit tests
    pytest tests/integration/       # run only integration tests
    pytest -v                       # verbose output
"""

from __future__ import annotations

import os
import sys


# Ensure project-root imports (domain, adapters, app, etc.) work from any tests/* depth.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
