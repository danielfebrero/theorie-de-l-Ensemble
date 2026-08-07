#!/usr/bin/env python3
"""Façade unittest-discovery de la suite de conformité."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import runpy
import sys
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "test_conformance.py"


def _load_source_module():
    spec = importlib.util.spec_from_file_location("m3c3_conformance_test_source", SOURCE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOURCE_MODULE = _load_source_module()


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str):
    return loader.loadTestsFromModule(SOURCE_MODULE)


if __name__ == "__main__":
    runpy.run_path(str(SOURCE), run_name="__main__")
