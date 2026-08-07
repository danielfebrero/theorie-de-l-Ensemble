#!/usr/bin/env python3
"""Validate REACH-MAX v2 profiles and the aggregate `all` profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from reach_max import validate_distribution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parent
    parser.add_argument("--distribution-root", type=Path, default=default_root)
    parser.add_argument("--repository-root", type=Path, default=default_root.parent)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable result")
    args = parser.parse_args()

    errors = validate_distribution(args.distribution_root, args.repository_root)
    result = {
        "ok": not errors,
        "distribution": str(args.distribution_root.resolve()),
        "repository": str(args.repository_root.resolve()),
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif errors:
        print("REACH-MAX validation failed:")
        for error in errors:
            print("- " + error)
    else:
        print("REACH-MAX v2 validation: OK (profiles core/openai/claude/copilot/cursor/mcp/ci/all)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
