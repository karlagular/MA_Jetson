"""Shared pytest configuration for test import paths."""

from __future__ import annotations

import os
import sys


# Ensure project-root imports (domain, adapters, app, etc.) work from any tests/* depth.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
