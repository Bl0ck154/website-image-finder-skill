#!/usr/bin/env python3
"""Explicit, bounded end-to-end smoke checks for free image-search providers.

This is a manual network diagnostic, not a CI test. It writes temporary project
data, reports provider-level outcomes, and removes downloaded images on exit.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

FREE_PROVIDERS = ("wikimedia", "openverse", "ddgs")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Required acknowledgement of real network requests")
    parser.add_argument("--provider", action="append", choices=FREE_PROVIDERS,
                        help="Repeatable; default is Wikimedia Commons only")
    parser.add_argument("--query", default="mountain lake", help="Public generic image-search query")
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=75, help="Per-provider timeout in seconds")
    return parser.parse_args(argv)


def check_options(args: argparse.Namespace) -> list[str]:
    if not args.live:
        raise ValueError("Pass --live to explicitly allow real network image searches")
    if not 1 <= args.max_results <= 20:
        raise ValueError("--max-results must be 1-20")
    if not 1 <= args.max_attempts <= 10:
        raise ValueError("--max-attempts must be 1-10")
    if not 10 <= args.timeout <= 180:
        raise ValueError("--timeout must be 10-180 seconds")
    if not args.query.strip() or len(args.query) > 120:
        raise ValueError("--query must contain 1-120 characters")
    return list(dict.fromkeys(args.provider or ["wikimedia"]))


def run_provider(
    provider: str, query: str, max_results: int, max_attempts: int,
    timeout: int, launcher: Path,
) -> dict[str, Any]:
    measured = time.monotonic()
    outcome: dict[str, Any] = {
        "provider": provider, "status": "failed", "unique_results": 0,
        "downloaded": 0, "download_attempts": 0, "finalized": False,
        "elapsed_seconds": None,
    }
    with tempfile.TemporaryDirectory(prefix="website-image-finder-smoke-") as dirname:
        root = Path(dirname)
        run = root / ".image-search" / "smoke"
        args = [
            sys.executable, str(launcher), "search", query,
            "--provider", provider, "--root", str(root),
            "--out", ".image-search/smoke",
            "--batch-size", "1", "--max-results", str(max_results),
            "--max-attempts", str(max_attempts),
            "--min-width", "300", "--min-height", "200",
            "--reuse-cache-hours", "0",
        ]
        env = os.environ.copy()
        env["WEBSITE_IMAGE_FINDER_AUTO_SETUP"] = "0"
        env.pop("SERPAPI_API_KEY", None)
        env.pop("SERPAPI_KEY", None)
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, env=env,
            )
            cache = run / "results-cache.json"
            if cache.is_file():
                data = json.loads(cache.read_text(encoding="utf-8"))
                summary = data.get("summary") or {}
                metrics = data.get("metrics") or {}
                outcome["unique_results"] = summary.get("unique_results", 0)
                outcome["downloaded"] = summary.get("downloaded_unique", 0)
                outcome["download_attempts"] = metrics.get("download_attempts", 0)
            if proc.returncode != 0:
                # Never echo arbitrary provider stderr: error messages could
                # contain third-party URLs or untrusted search metadata.
                if provider == "ddgs" and ("Missing ddgs" in proc.stderr or
                                           "No module named 'ddgs'" in proc.stderr):
                    outcome["reason"] = "optional DDGS dependency is missing; run python scripts/skill.py setup"
                else:
                    outcome["reason"] = f"search exit code {proc.returncode}"
            elif not cache.is_file():
                outcome["reason"] = "search did not produce a cache"
            else:
                selected = next(
                    (candidate for candidate in data["results"]
                     if candidate.get("status") == "downloaded"), None,
                )
                if selected is None:
                    outcome["reason"] = "no downloaded candidates"
                else:
                    final = subprocess.run(
                        [sys.executable, str(launcher), "finalize", "--root", str(root),
                         "--cache", str(cache), "--candidate", str(selected["rank"]),
                         "--output", "public/images/smoke.webp"],
                        capture_output=True, text=True, timeout=20, env=env,
                    )
                    target = root / "public" / "images" / "smoke.webp"
                    outcome["finalized"] = final.returncode == 0 and target.is_file()
                    outcome["status"] = "passed" if outcome["finalized"] else "failed"
                    if not outcome["finalized"]:
                        outcome["reason"] = f"finalize exit code {final.returncode}"
        except subprocess.TimeoutExpired:
            outcome["reason"] = f"operation exceeded timeout ({timeout}s)"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            outcome["reason"] = f"local diagnostic failed ({type(exc).__name__})"
    outcome["elapsed_seconds"] = round(time.monotonic() - measured, 3)
    return outcome


def main() -> int:
    args = parse_args()
    try:
        providers = check_options(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    launcher = Path(__file__).with_name("skill.py")
    results = [
        run_provider(provider, args.query, args.max_results,
                     args.max_attempts, args.timeout, launcher)
        for provider in providers
    ]
    report = {
        "schema_version": 1,
        "purpose": "bounded-live-free-provider-smoke",
        "query": args.query,
        "results": results,
        "passed": sum(r["status"] == "passed" for r in results),
        "failed": sum(r["status"] != "passed" for r in results),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
