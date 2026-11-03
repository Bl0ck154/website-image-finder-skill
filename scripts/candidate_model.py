"""Candidate records shared by search providers, downloads and cache handling."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import hashlib
from datetime import datetime, timezone
from typing import Any
from common import SkillError, canonical_url, domain_of, validate_remote_url_syntax

@dataclass
class Candidate:
    id: str
    rank: int
    provider: str
    provider_position: int
    queries: list[str]
    title: str
    image_url: str
    thumbnail_url: str
    source_page_url: str
    source_domain: str
    source_label: str
    reported_width: int | None
    reported_height: int | None
    license_url: str | None = None
    license_tag: str | None = None
    is_product: bool | None = None
    score: float = 0.0
    local_file: str | None = None
    original_file: str | None = None
    downloaded_url: str | None = None
    content_type: str | None = None
    source_bytes: int | None = None
    actual_width: int | None = None
    actual_height: int | None = None
    has_alpha: bool | None = None
    sha256: str | None = None
    dhash: str | None = None
    status: str = "found"
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    batch: int | None = None


@dataclass
class DdgsSearchBatch:
    candidates: list[Candidate]
    ddgs_version: str
    requested_backend: str
    actual_sources: list[str]


def candidate_from_dict(payload: dict[str, Any]) -> Candidate:
    allowed = {item.name for item in fields(Candidate)}
    return Candidate(**{key: value for key, value in payload.items() if key in allowed})


def int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_result_url(value: Any, *, required: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise SkillError("missing result URL")
        return ""
    try:
        return validate_remote_url_syntax(raw)
    except SkillError:
        if required:
            raise
        return ""


def make_candidate(provider: str, query: str, position: int, item: dict[str, Any]) -> Candidate | None:
    if provider == "serpapi":
        try:
            image_url = safe_result_url(item.get("original"), required=True)
        except SkillError:
            return None
        page_url = safe_result_url(item.get("link"))
        if item.get("unsafe") is True:
            return None
        key = hashlib.sha1(canonical_url(image_url).encode("utf-8", "replace")).hexdigest()[:12]
        return Candidate(
            id=f"img-{key}",
            rank=position,
            provider="serpapi-google-images",
            provider_position=int_or_none(item.get("position")) or position,
            queries=[query],
            title=str(item.get("title") or "").strip(),
            image_url=image_url,
            thumbnail_url=safe_result_url(item.get("thumbnail")),
            source_page_url=page_url,
            source_domain=domain_of(page_url),
            source_label=str(item.get("source") or "").strip(),
            reported_width=int_or_none(item.get("original_width")),
            reported_height=int_or_none(item.get("original_height")),
            license_url=str(item.get("license_details_url") or "").strip() or None,
            license_tag=str(item.get("tag") or "").strip() or None,
            is_product=bool(item.get("is_product")) if item.get("is_product") is not None else None,
        )

    try:
        image_url = safe_result_url(item.get("image"), required=True)
    except SkillError:
        return None
    page_url = safe_result_url(item.get("url"))
    key = hashlib.sha1(canonical_url(image_url).encode("utf-8", "replace")).hexdigest()[:12]
    return Candidate(
        id=f"img-{key}",
        rank=position,
        provider="ddgs-images",
        provider_position=position,
        queries=[query],
        title=str(item.get("title") or "").strip(),
        image_url=image_url,
        thumbnail_url=safe_result_url(item.get("thumbnail")),
        source_page_url=page_url,
        source_domain=domain_of(page_url),
        source_label=str(item.get("source") or "").strip(),
        reported_width=int_or_none(item.get("width")),
        reported_height=int_or_none(item.get("height")),
    )


def make_openverse_candidate(query: str, position: int, item: dict[str, Any]) -> Candidate | None:
    """Normalize Openverse image results without treating licenses as verified reuse permission."""
    try:
        image_url = safe_result_url(item.get("url"), required=True)
    except SkillError:
        return None
    page_url = safe_result_url(item.get("foreign_landing_url") or item.get("detail_url"))
    key = hashlib.sha1(canonical_url(image_url).encode("utf-8", "replace")).hexdigest()[:12]
    return Candidate(
        id=f"img-{key}",
        rank=position,
        provider="openverse",
        provider_position=position,
        queries=[query],
        title=str(item.get("title") or "").strip(),
        image_url=image_url,
        thumbnail_url=safe_result_url(item.get("thumbnail")),
        source_page_url=page_url,
        source_domain=domain_of(page_url),
        source_label=str(item.get("provider") or item.get("source") or "").strip(),
        reported_width=int_or_none(item.get("width")),
        reported_height=int_or_none(item.get("height")),
        license_url=str(item.get("license_url") or "").strip() or None,
        license_tag=str(item.get("license") or "").strip() or None,
    )
