#!/usr/bin/env python3
"""Deterministic local review shortlist from downloaded image metadata.

This is a technical ranking helper, not a visual understanding or license model.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

from common import SkillError, atomic_write_json, ensure_within_root, resolve_under_root, unicode_words


def technical_assessment(item: Any, run_dir: Path, orientation: str) -> dict[str, Any]:
    """Score observable image properties; leave subject relevance to the agent."""
    from PIL import Image, ImageFilter, ImageStat
    import warnings

    local_file = str(getattr(item, "local_file", "") or "")
    if not local_file or getattr(item, "status", "") != "downloaded":
        raise SkillError("only downloaded candidates can be technically reviewed")
    path = ensure_within_root(run_dir / local_file, run_dir, label="review image")
    if not path.is_file():
        raise SkillError(f"candidate image is missing: {path.name}")

    Image.MAX_IMAGE_PIXELS = 30_000_000
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            thumbnail = image.convert("RGB")
            thumbnail.thumbnail((256, 256))
            mono = thumbnail.convert("L")
            stats = ImageStat.Stat(mono)
            contrast = round(float(stats.stddev[0]), 2)
            edges = mono.filter(ImageFilter.FIND_EDGES)
            edge_mean = round(float(ImageStat.Stat(edges).mean[0]), 2)
    title_words = unicode_words(str(getattr(item, "title", "")))
    query_words = set().union(*(
        unicode_words(query) for query in (getattr(item, "queries", []) or []) if isinstance(query, str)
    ))
    matched = sorted(query_words & title_words)
    ratio = width / max(height, 1)
    size_points = min(35.0, max(0.0, 9.0 * math.log2(width * height / 250_000 + 1)))
    if orientation == "any":
        shape_points = 10.0
        shape_reason = "no aspect ratio preference"
    else:
        good = (
            (orientation == "wide" and ratio >= 1.25)
            or (orientation == "tall" and ratio <= 0.80)
            or (orientation == "square" and 0.85 <= ratio <= 1.18)
        )
        shape_points = 20.0 if good else -10.0
        shape_reason = "matches requested aspect ratio" if good else "aspect ratio differs from request"

    relevance_points = min(20.0, 5.0 * len(matched))
    source_page = bool(getattr(item, "source_page_url", ""))
    source_points = 10.0 if source_page else 0.0
    license_metadata = bool(getattr(item, "license_url", "") or getattr(item, "license_tag", ""))
    license_points = 5.0 if license_metadata else 0.0
    rank_points = min(10.0, max(0.0, 10.0 - (int(getattr(item, "provider_position", 1)) - 1) * 0.2))
    score = round(max(0.0, min(100.0,
        size_points + shape_points + relevance_points + source_points + license_points + rank_points
    )), 1)

    reasons = [f"validated local raster: {width}x{height}", shape_reason]
    if matched:
        reasons.append("title matches search words: " + ", ".join(matched[:5]))
    if source_page:
        reasons.append("source page recorded")
    if license_metadata:
        reasons.append("license information available; verify original source")
    if contrast < 9:
        reasons.append("low contrast: may be intentional for artwork or backgrounds")
    if edge_mean < 3:
        reasons.append("low edge detail: inspect visually for intentional flat artwork or blur")

    return {
        "candidate_id": str(getattr(item, "id", "")),
        "rank": int(getattr(item, "rank", 0)),
        "provider": str(getattr(item, "provider", "")),
        "local_file": local_file,
        "technical_score": score,
        "score_breakdown": {
            "resolution": round(size_points, 1),
            "aspect_ratio": shape_points,
            "title_overlap": relevance_points,
            "source_page": source_points,
            "license_metadata": license_points,
            "provider_rank": round(rank_points, 1),
        },
        "measured": {
            "width": width,
            "height": height,
            "contrast_stddev": contrast,
            "edge_mean": edge_mean,
            "has_alpha": has_alpha,
        },
        "reasons": reasons,
        "visual_relevance_verified": False,
        "reuse_rights_verified": False,
    }


def build_review_report(candidates: list[Any], run_dir: Path, orientation: str = "any") -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for candidate in candidates:
        if getattr(candidate, "status", "") != "downloaded":
            continue
        try:
            scored.append(technical_assessment(candidate, run_dir, orientation))
        except Exception as exc:
            errors.append({
                "candidate_id": str(getattr(candidate, "id", "")),
                "error": str(exc)[:250],
            })
    scored.sort(key=lambda item: (-item["technical_score"], item["rank"]))
    return {
        "schema_version": 1,
        "scoring_method": "deterministic-technical-metadata-v1",
        "orientation": orientation,
        "scored_count": len(scored),
        "candidates": scored,
        "errors": errors,
        "notice": (
            "Scores cover measured dimensions, aspect ratio and source metadata. "
            "They DO NOT measure artistic quality, relevance, copyright permission or licensing. "
            "Inspect the contact sheet and original source before publishing."
        ),
    }


def save_review_report(
    candidates: list[Any], run_dir: Path, orientation: str = "any", batch: int | None = None,
) -> Path:
    run_dir = run_dir.resolve()
    report = build_review_report(candidates, run_dir, orientation)
    file_name = f"review-batch-{batch:02d}.json" if batch is not None else "review-all.json"
    path = run_dir / file_name
    atomic_write_json(path, report)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--run", required=True, help="A private .image-search run directory")
    parser.add_argument("--top", type=int, default=5, help="Recommended candidates to print (1-50)")
    args = parser.parse_args()
    if not 1 <= args.top <= 50:
        parser.error("--top must be between 1 and 50")
    root = Path(args.root).resolve()
    private = resolve_under_root(".image-search", root)
    run_dir = ensure_within_root(resolve_under_root(args.run, root), private)
    import json
    from image_search import candidate_from_dict

    cache = run_dir / "results-cache.json"
    if not cache.is_file():
        print("Search cache not found inside run directory", file=sys.stderr)
        return 2
    payload = json.loads(cache.read_text(encoding="utf-8"))
    candidates = [candidate_from_dict(item) for item in payload.get("results", []) if isinstance(item, dict)]
    orientation = payload.get("search_settings", {}).get("orientation", "any")
    output = save_review_report(candidates, run_dir, orientation)
    report = json.loads(output.read_text(encoding="utf-8"))
    print(f"Technical shortlist: {report['scored_count']} downloaded candidates")
    print(f"Private review report: {output}")
    for item in report["candidates"][:args.top]:
        print(f"  #{item['rank']}: {item['technical_score']:.1f}/100 "
              f"({item['measured']['width']}x{item['measured']['height']})")
    print("Inspect images and verify image rights; the technical score is not a creative judgement.")
    return 0 if report["scored_count"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
