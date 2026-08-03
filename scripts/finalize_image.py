#!/usr/bin/env python3
"""Convert a selected candidate into an optimized local website asset."""
from __future__ import annotations

from finalize_args import parse_args
from finalize_run import run


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
