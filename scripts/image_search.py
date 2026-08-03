#!/usr/bin/env python3
"""Search image providers, cache results, and create review batches."""
from __future__ import annotations

from image_search_core import *
from image_search_assets import *
from image_search_args import parse_args, validate_args
from image_search_run import run


def main() -> int:
    args = parse_args()
    validate_args(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
