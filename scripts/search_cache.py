"""Write and reuse private search-result metadata without repeating provider calls."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from candidate_model import Candidate, now_iso
from common import SkillError, atomic_write_json, resolve_under_root

def cache_summary(candidates: list[Candidate]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    for candidate in candidates:
        statuses[candidate.status] = statuses.get(candidate.status, 0) + 1
    return {
        "unique_results": len(candidates),
        "downloaded_unique": statuses.get("downloaded", 0),
        "remaining_unattempted": statuses.get("found", 0),
        "batches": max((candidate.batch or 0 for candidate in candidates), default=0),
        "statuses": statuses,
    }


def write_cache(cache_path: Path, payload: dict[str, Any], candidates: list[Candidate]) -> None:
    payload["updated_at"] = now_iso()
    payload["summary"] = cache_summary(candidates)
    payload["results"] = [asdict(candidate) for candidate in candidates]
    atomic_write_json(cache_path, payload)


def find_reusable_cache(
    root: Path,
    queries: list[str],
    settings: dict[str, Any],
    provider: str,
    hours: int,
    exclude: Path,
) -> dict[str, Any] | None:
    """Reuse search metadata only for identical settings; never reuse old downloaded files."""
    base = root / ".image-search"
    if hours < 1 or not base.is_dir():
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    matches: list[tuple[datetime, dict[str, Any]]] = []
    for candidate_path in base.glob("*/results-cache.json"):
        try:
            path = resolve_under_root(candidate_path, root, label="reusable cache")
            if path.parent == exclude:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (payload.get("schema_version") != 3 or
                payload.get("tool") != "website-image-finder" or
                payload.get("requested_provider") != provider or
                payload.get("queries") != queries or
                payload.get("search_settings") != settings or
                not payload.get("results") or not payload.get("providers_used")):
                continue
            created = datetime.fromisoformat(payload["created_at"])
            if created.tzinfo is None or not cutoff <= created <= datetime.now(timezone.utc):
                continue
            matches.append((created, payload))
        except (OSError, ValueError, TypeError, KeyError, SkillError):
            continue
    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]
