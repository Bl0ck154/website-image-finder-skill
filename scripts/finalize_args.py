#!/usr/bin/env python3
"""Argument parsing and source resolution for image finalization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import SkillError, ensure_within_root, resolve_under_root

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Input raster image path")
    source.add_argument("--cache", "--manifest", dest="cache", help="Search results cache; combine with --candidate")
    parser.add_argument("--candidate", help="Candidate id or numeric rank when --cache is used")
    parser.add_argument("--root", default=".", help="Project root; input/output must stay inside it")
    parser.add_argument("--output", required=True, help="Output .webp, .jpg/.jpeg, or .png path")
    parser.add_argument("--max-width", type=int, default=1800)
    parser.add_argument("--max-height", type=int, default=1800)
    parser.add_argument("--max-pixels", type=int, default=30_000_000)
    parser.add_argument("--max-input-mb", type=int, default=40, help="Reject local inputs larger than this")
    parser.add_argument("--quality", type=int, default=84)
    parser.add_argument("--jpeg-background", default="#ffffff", help="Background used when flattening alpha to JPEG")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-first-frame", action="store_true")
    parser.add_argument("--no-sidecar", action="store_true", help="Do not write <output>.source.json when using a search cache")
    return parser.parse_args()


def find_candidate(payload: dict[str, Any], selector: str) -> dict[str, Any]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise SkillError("search cache results must be a list")
    for candidate in results:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("id")) == selector or str(candidate.get("rank")) == selector:
            return candidate
    raise SkillError(f"candidate not found in search cache: {selector}")


def resolve_source(args: argparse.Namespace, root: Path) -> tuple[Path, dict[str, Any] | None, Path | None]:
    if args.input:
        source = resolve_under_root(args.input, root, label="input")
        return source, None, None
    if not args.candidate:
        raise SkillError("--candidate is required with --cache")
    manifest_path = resolve_under_root(str(args.cache), root, label="search cache")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillError(f"cannot read search cache: {manifest_path}") from exc
    candidate = find_candidate(payload, str(args.candidate))
    local_file = candidate.get("local_file")
    if not local_file or candidate.get("status") != "downloaded":
        raise SkillError("selected candidate has no downloaded local file")
    source = ensure_within_root(manifest_path.parent / str(local_file), root, label="candidate file")
    return source, candidate, manifest_path
