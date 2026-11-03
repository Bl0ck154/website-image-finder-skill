#!/usr/bin/env python3
"""Download the next review batch from an existing local search cache without calling a search provider."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from review_candidates import save_review_report

from common import SkillError, atomic_write_json, redact, resolve_under_root, ensure_within_root, prepare_private_workdir
from image_search import (
    CACHE_FILENAME,
    cache_summary,
    candidate_from_dict,
    create_session,
    download_next_batch,
    write_batch_outputs,
    write_cache,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Existing search run directory containing results-cache.json")
    parser.add_argument("--root", default=".", help="Project root; run directory must stay inside it")
    parser.add_argument("--count", type=int, default=12, help="Number of additional unique candidates to download")
    parser.add_argument("--max-attempts", type=int, default=30, help="Maximum additional network download attempts")
    parser.add_argument("--retry-failed", action="store_true", help="Retry failed and too-small candidates (use size overrides if needed)")
    parser.add_argument("--min-width", type=int, help="Override cached minimum width for this batch")
    parser.add_argument("--min-height", type=int, help="Override cached minimum height for this batch")
    return parser.parse_args()


def load_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillError(f"cannot read search cache: {path}") from exc
    if payload.get("tool") != "website-image-finder" or int(payload.get("schema_version", 0)) < 3:
        raise SkillError("unsupported or invalid search cache")
    if not isinstance(payload.get("results"), list) or not isinstance(payload.get("download_settings"), dict):
        raise SkillError("search cache is missing results or download settings")
    return payload


def main() -> int:
    args = parse_args()
    session = None
    try:
        if args.count < 1 or args.count > 50:
            raise SkillError("--count must be between 1 and 50")
        if args.max_attempts < args.count or args.max_attempts > 200:
            raise SkillError("--max-attempts must be between --count and 200")

        root = Path(args.root).resolve()
        if not root.is_dir():
            raise SkillError(f"project root does not exist: {root}")
        prepare_private_workdir(root)
        private_root = resolve_under_root(".image-search", root)
        run_dir = ensure_within_root(
            resolve_under_root(args.run, root, label="search run directory"),
            private_root,
            label="private search run directory",
        )
        if run_dir == private_root:
            raise SkillError("--run must refer to an individual private search run")
        if not run_dir.is_dir():
            raise SkillError(f"search run directory does not exist: {run_dir}")
        cache_path = run_dir / CACHE_FILENAME
        payload = load_cache(cache_path)
        candidates = [candidate_from_dict(item) for item in payload["results"] if isinstance(item, dict)]
        settings = dict(payload["download_settings"])
        for key in ("min_width", "min_height"):
            value = getattr(args, key)
            if value is not None:
                if value < 1:
                    raise SkillError(f"--{key.replace('_', '-')} must be positive")
                settings[key] = value

        session = create_session()
        downloaded, attempts = download_next_batch(
            session,
            candidates,
            run_dir,
            settings,
            args.count,
            args.max_attempts,
            retry_failed=args.retry_failed,
        )
        sheet = None
        batch_file = None
        review_file = None
        if downloaded:
            batch_number = downloaded[0].batch or 1
            sheet, batch_file = write_batch_outputs(downloaded, run_dir, batch_number)
            review_file = save_review_report(downloaded, run_dir, payload.get("search_settings", {}).get("orientation", "any"), batch_number)
        write_cache(cache_path, payload, candidates)

        summary = cache_summary(candidates)
        if not downloaded:
            print("No additional downloadable candidates were produced from the existing cache.")
            print(f"Remaining unattempted: {summary['remaining_unattempted']}")
            print(f"Search cache: {cache_path}")
            return 3

        print("Search provider calls: 0")
        print(f"Downloaded in new batch: {len(downloaded)} ({attempts} network attempts)")
        if batch_file:
            print(f"Candidate list: {run_dir / batch_file}")
        if sheet:
            print(f"Contact sheet: {run_dir / sheet}")
        if review_file:
            print(f"Technical shortlist: {review_file}")
        print(f"Remaining unattempted: {summary['remaining_unattempted']}")
        print(f"Search cache: {cache_path}")
        return 0
    except SkillError as exc:
        print(f"Error: {redact(str(exc))}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {redact(f'{type(exc).__name__}: {exc}')}", file=sys.stderr)
        return 2
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
