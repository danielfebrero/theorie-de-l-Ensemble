"""Minimal command-line interface for verification, replay and exploration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .audit import AuditLog
from .constants import canonical_invariants
from .engine import M3C3Runtime
from .errors import M3C3Error
from .explore import explore_transitions
from .replay import replay_file


def _signing_key(value: str | None, *, required: bool) -> bytes | None:
    encoded = value or os.environ.get("M3C3_SIGNING_KEY_HEX")
    if not encoded:
        if required:
            raise ValueError(
                "provide --key-hex or set M3C3_SIGNING_KEY_HEX (at least 32 bytes)"
            )
        return None
    try:
        key = bytes.fromhex(encoded)
    except ValueError as exc:
        raise ValueError("signing key must be hexadecimal") from exc
    if len(key) < 32:
        raise ValueError("signing key must contain at least 32 bytes")
    return key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="m3c3-runtime")
    parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="create and export one active runtime")
    demo.add_argument("--key-hex")
    demo.add_argument("--scope", default="cli-demo")
    demo.add_argument("--membrane", choices=("A1", "A2", "A3"), default="A1")
    demo.add_argument("--audit", type=Path)
    demo.add_argument("--output", type=Path)

    verify = subparsers.add_parser("verify-audit", help="verify a JSONL hash chain")
    verify.add_argument("path", type=Path)
    verify.add_argument("--expected-head")
    verify.add_argument("--expected-length", type=int)

    replay = subparsers.add_parser(
        "replay", help="restore verified snapshots from a JSONL audit"
    )
    replay.add_argument("path", type=Path)
    replay.add_argument("--key-hex")
    replay.add_argument("--expected-head")
    replay.add_argument("--expected-length", type=int)
    replay.add_argument("--output", type=Path)

    explore = subparsers.add_parser(
        "explore", help="run bounded S1-S5 transition exploration"
    )
    explore.add_argument("--max-depth", type=int, default=6)
    explore.add_argument("--max-states", type=int, default=512)

    subparsers.add_parser("invariants", help="print frozen v1 kernel invariants")
    return parser


def _emit(value: object, output: Path | None = None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            key = _signing_key(args.key_hex, required=True)
            assert key is not None
            runtime = M3C3Runtime(
                signing_key=key,
                known_m3c3=True,
                audit_path=args.audit,
            )
            runtime.activate_scope(args.scope, membrane=args.membrane, actor="cli")
            _emit(runtime.export(), args.output)
        elif args.command == "verify-audit":
            log = AuditLog.load(args.path)
            _emit(
                {
                    "verified": log.verify(
                        expected_head=args.expected_head,
                        expected_length=args.expected_length,
                    ),
                    "length": log.length,
                    "head": log.head,
                    "externally_anchored": (
                        args.expected_head is not None
                        or args.expected_length is not None
                    ),
                }
            )
        elif args.command == "replay":
            key = _signing_key(args.key_hex, required=False)
            result = replay_file(
                args.path,
                signing_key=key,
                expected_head=args.expected_head,
                expected_length=args.expected_length,
            )
            _emit(result.to_dict(), args.output)
        elif args.command == "explore":
            report = explore_transitions(
                max_depth=args.max_depth, max_states=args.max_states
            )
            _emit(report.to_dict())
            return 0 if report.safe else 2
        elif args.command == "invariants":
            _emit(canonical_invariants())
        else:
            parser.error(f"unknown command: {args.command}")
    except (M3C3Error, OSError, ValueError) as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
        return 1
    return 0
