#!/usr/bin/env python3
"""Validate a Hermes Pets custom pet package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes_pet.custom_pets import inspect_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Package, hatch-pet run, or sprites folder to validate.")
    parser.add_argument("--name", default=None, help="Optional name to validate against.")
    args = parser.parse_args()

    try:
        package = inspect_package(args.path, name=args.name)
    except Exception as exc:
        print(f"Custom pet validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Custom pet validation passed: {package.name}")
    print(f"Format: {package.source_format}")
    print(f"States: {', '.join(sorted(package.states))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
