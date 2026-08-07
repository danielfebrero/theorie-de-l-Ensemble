#!/usr/bin/env python3
"""Entrée canonique de la suite de conformité M3C3."""

from pathlib import Path
import runpy
import sys


SUITE = Path(__file__).resolve().with_name("run_suite.py")

if __name__ == "__main__":
    sys.path.insert(0, str(SUITE.parent))
    runpy.run_path(str(SUITE), run_name="__main__")
