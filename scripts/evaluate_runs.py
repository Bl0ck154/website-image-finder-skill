#!/usr/bin/env python3
"""Offline, privacy-safe summary of recorded image search runs.

No network calls and no subjective relevance claims. This is an operational
benchmark; use a separate human review for usefulness or visual relevance.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import SkillError, atomic_write_json, ensure_within_root, resolve_under_root


def summarize_cache(cache: dict[str, Any], run_name: str) -> dict[str, Any]:
    if cache.get("tool") != "website-image-finder" or not isinstance(cache.get("results"), list):
        raise SkillError("invalid image search cache")
    results = [candidate for candidate in cache["results"] if isinstance(candidate, dict)]
    statuses = Counter(str(candidate.get("status") or "unknown") for candidate in results)
    metrics = cache.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    calls = metrics.get("provider_calls")
    if not isinstance(calls, dict):
        calls = None
    else:
        calls = {
            str(provider): int(amount)
            for provider, amount in calls.items()
            if type(amount) is int and amount >= 0
        }
    elapsed = metrics.get("elapsed_seconds")
    elapsed = round(float(elapsed), 3) if isinstance(elapsed, (int, float)) and elapsed >= 0 else None
    return {
        "run": run_name,
        "requested_provider": str(cache.get("requested_provider") or "unknown"),
        "providers_used": list(cache.get("providers_used") or []),
        "queries": len(cache.get("queries") or []),
        "result_count": len(results),
        "downloaded": statuses.get("downloaded", 0),
        "duplicates": statuses.get("duplicate", 0),
        "failed": statuses.get("failed", 0),
        "remaining": statuses.get("found", 0),
        "status_counts": dict(sorted(statuses.items())),
        "provider_calls": calls,
        "elapsed_seconds": elapsed,
        "cache_reused": metrics.get("cache_reused") if "cache_reused" in metrics else None,
        "warnings_count": len(cache.get("warnings") or []),
        "complete_metrics": calls is not None and elapsed is not None,
    }


def aggregate_summaries(runs: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed = [run["elapsed_seconds"] for run in runs if run["elapsed_seconds"] is not None]
    calls: Counter[str] = Counter()
    observed_calls = 0
    for run in runs:
        if run["provider_calls"] is not None:
            observed_calls += 1
            calls.update(run["provider_calls"])
    successes = sum(run["downloaded"] > 0 for run in runs)
    return {
        "runs": len(runs),
        "runs_with_download": successes,
        "runs_without_download": len(runs) - successes,
        "unique_search_results_total": sum(run["result_count"] for run in runs),
        "downloaded_total": sum(run["downloaded"] for run in runs),
        "duplicate_total": sum(run["duplicates"] for run in runs),
        "failed_total": sum(run["failed"] for run in runs),
        "provider_calls_total": dict(sorted(calls.items())) if observed_calls else None,
        "provider_call_data_available_for": observed_calls,
        "cache_reused_runs": sum(run["cache_reused"] is True for run in runs),
        "median_elapsed_seconds": round(statistics.median(elapsed), 3) if elapsed else None,
        "timing_data_available_for": len(elapsed),
    }


def load_runs(root: Path, run_paths: list[str], latest: int) -> list[dict[str, Any]]:
    private = resolve_under_root(".image-search", root)
    if not private.is_dir():
        raise SkillError("No image-search run directory found")
    paths = []
    if run_paths:
        for value in run_paths:
            run = ensure_within_root(resolve_under_root(value, root), private, label="search run")
            paths.append(run / "results-cache.json")
    else:
        paths = sorted(
            private.glob("*/results-cache.json"),
            key=lambda value: value.stat().st_mtime,
            reverse=True,
        )[:latest]
    out = []
    for path in paths:
        safe_path = ensure_within_root(path, private, label="search cache")
        try:
            payload = json.loads(safe_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SkillError(f"Cannot read cache for {safe_path.parent.name}") from exc
        out.append(summarize_cache(payload, safe_path.parent.name))
    if not out:
        raise SkillError("No saved search runs available")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--run", action="append", default=[], help="Specific run directory; repeatable")
    parser.add_argument("--latest", type=int, default=10, help="Latest N runs (1-100) when --run is omitted")
    parser.add_argument("--output", help="Private JSON report output below .image-search/")
    args = parser.parse_args()
    if not 1 <= args.latest <= 100:
        parser.error("--latest must be 1-100")
    try:
        root = Path(args.root).resolve()
        runs = load_runs(root, args.run, args.latest)
        report = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "method": "offline-cache-observations",
            "summary": aggregate_summaries(runs),
            "runs": runs,
            "caveat": (
                "These are search/download operational observations, not measured image relevance, "
                "agent time saved, human preference, user demand or verified publication rights. "
                "Older caches may lack timing or request counts."
            ),
        }
        private = resolve_under_root(".image-search", root)
        if args.output:
            output = ensure_within_root(resolve_under_root(args.output, root), private, label="report")
            atomic_write_json(output, report)
            print(f"Saved private evaluation: {output}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (SkillError, OSError, ValueError, TypeError) as exc:
        print(f"Error: {str(exc)[:300]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
