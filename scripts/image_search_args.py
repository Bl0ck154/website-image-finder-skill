#!/usr/bin/env python3
"""CLI argument definitions and validation for Website Image Finder."""
from __future__ import annotations

import argparse

from common import SkillError
from image_search_core import region_to_google

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Primary image-search query")
    parser.add_argument("--extra-query", action="append", default=[], help="Additional query; repeatable")
    parser.add_argument("--provider", choices=["auto", "serpapi", "ddgs"], default="auto")
    parser.add_argument("--no-provider-fallback", action="store_true", help="Do not fall back from SerpApi to DDGS")
    parser.add_argument("--ddgs-backend", choices=["auto", "bing", "duckduckgo"], default="auto")
    parser.add_argument("--root", default=".", help="Project root; output must stay inside it")
    parser.add_argument("--out", default=None, help="Output directory; default is .image-search/<slug>-<UTC timestamp>")
    parser.add_argument("--overwrite-output", action="store_true", help="Allow a non-empty output directory")
    parser.add_argument("--max-results", type=int, default=60, help="Maximum results requested per query per page")
    parser.add_argument("--pages", type=int, default=1, help="Number of result pages per query (1-3; each SerpApi page may use a search credit)")
    parser.add_argument("--page", type=int, default=1, help="Starting provider page, 1-based")
    parser.add_argument("--batch-size", "--keep", dest="batch_size", type=int, default=12, help="Candidates in the first review batch; 0 means URLs only")
    parser.add_argument("--max-attempts", type=int, default=30, help="Maximum network download attempts for the first batch")
    parser.add_argument("--download", type=int, default=None, help="Deprecated alias for --max-attempts")
    parser.add_argument("--region", default="lt-lt", help="Region-language, e.g. lt-lt, ua-uk, us-en")
    parser.add_argument("--min-width", type=int, default=800)
    parser.add_argument("--min-height", type=int, default=500)
    parser.add_argument("--max-mb", type=int, default=12)
    parser.add_argument("--max-pixels", type=int, default=30_000_000)
    parser.add_argument("--orientation", choices=["any", "square", "tall", "wide"], default="any")
    parser.add_argument("--image-type", choices=["any", "photo", "clipart", "lineart", "transparent", "animated"], default="any")
    parser.add_argument("--size", choices=["any", "small", "medium", "large", "wallpaper"], default="any")
    parser.add_argument("--color", default="any", help="any, bw, red, orange, yellow, green, teal, blue, purple, pink, white, gray, black, brown")
    parser.add_argument("--safe-search", choices=["active", "moderate", "off"], default="active")
    parser.add_argument("--time-limit", choices=["any", "d", "w", "m", "y"], default="any")
    parser.add_argument("--license", dest="license_filter", choices=["any", "share", "commercial", "modify", "commercial-modify", "creative-commons", "commercial-other"], default="any")
    parser.add_argument("--preferred-domain", action="append", default=[], help="Boost this source domain; repeatable")
    parser.add_argument("--allowed-domain", action="append", default=[], help="Keep only this source/image domain; repeatable")
    parser.add_argument("--blocked-domain", action="append", default=[], help="Exclude this source/image domain; repeatable")
    parser.add_argument("--near-duplicate-distance", type=int, default=5)
    parser.add_argument("--allow-first-frame", action="store_true", help="Flatten the first frame of animated raster images")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.download is not None:
        args.max_attempts = args.download
    if not args.query.strip():
        raise SkillError("query cannot be empty")
    all_queries = [args.query, *args.extra_query]
    if len(all_queries) > 5:
        raise SkillError("at most 5 total queries are allowed per run")
    if any(len(value.strip()) > 300 for value in all_queries):
        raise SkillError("each query must be 300 characters or fewer")
    if any(len(values) > 50 for values in (args.preferred_domain, args.allowed_domain, args.blocked_domain)):
        raise SkillError("each domain filter list is limited to 50 entries")
    if args.max_results < 1 or args.max_results > 100:
        raise SkillError("--max-results must be between 1 and 100")
    if args.pages < 1 or args.pages > 3 or args.page < 1 or args.page > 20:
        raise SkillError("--pages must be 1-3 and --page must be between 1 and 20")
    if args.batch_size < 0 or args.batch_size > 50 or args.max_attempts < 0 or args.max_attempts > 200:
        raise SkillError("invalid batch/attempt limits")
    if args.batch_size > 0 and args.max_attempts < args.batch_size:
        raise SkillError("--max-attempts must be at least --batch-size; use --batch-size 0 for URLs only")
    if args.min_width < 1 or args.min_height < 1 or args.max_mb < 1 or args.max_mb > 100:
        raise SkillError("invalid size limits")
    if args.max_pixels < 1_000_000 or args.max_pixels > 200_000_000:
        raise SkillError("--max-pixels must be between 1,000,000 and 200,000,000")
    if not 0 <= args.near_duplicate_distance <= 16:
        raise SkillError("--near-duplicate-distance must be 0-16")
    valid_colors = {"any", "bw", "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink", "white", "gray", "black", "brown"}
    if args.color.lower() not in valid_colors:
        raise SkillError(&"unsupported color: {args.color}")
    args.color = args.color.lower()
    region_to_google(args.region)
