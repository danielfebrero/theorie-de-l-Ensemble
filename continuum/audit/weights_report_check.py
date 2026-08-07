#!/usr/bin/env python3
"""Entrée canonique vers le validateur des rapports d'intégration de poids."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys


VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / "weights"
    / "integration-reports"
    / "validate.py"
)

if __name__ == "__main__":
    sys.path.insert(0, str(VALIDATOR.parent))
    runpy.run_path(str(VALIDATOR), run_name="__main__")
