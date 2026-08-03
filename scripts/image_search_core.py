#!/usr/bin/env python3
"""Search image providers, cache results, download one review batch, and build compact review files."""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import sys
import tempfile
import warnings
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from common import (
    VERSION,
    SkillError,
    atomic_write_json,
    canonical_url,
    domain_of,
    host_matches,
    normalize_domain,
    origin_referer,
    redact,
    resolve_under_root,
    safe_redirect,
    unicode_words,
    validate_public_url,
    validate_remote_url_syntax,
)

USER_AGENT = "WebsiteImageFinder/0.2.0 (+Agent Skill; image asset research)"
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
MAX_REDIRECTS = 5
CACHE_FILENAME = "results-cache.json"


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
    downloaded_url: str | None = None
    content_type: str | None = None
    source_bytes: int | None = None
    actual_width: int | None
    actual_height: int | None
    has_alpha: bool | None = None
    sha256: str | None = None
    dhash: str | None = None
    status: str = "found"
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    batch: int | None = None


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


def slugify(value: str, max_len: int = 64) -> str:
    normalized = value.casefold().strip()
    normalized = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-_")
    ascii_slug = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_slug = re.sub(r"[^a-z0-9-]+", "-", ascii_slug).strip("-")
    return (ascii_slug or "image")[:max_len].rstrip("-")


def region_to_google(region: str) -> tuple[str, str]:
    normalized = region.strip().lower().replace("_", "-")
    match = re.fullmatch(r"([a-z]}{2})-([a-z]}{2,3})", normalized)
    if not match:
        raise SkillError("region must look like lt-lt, ua-uk, or us-en")
    return match.group(1), match.group(2)


def serpapi_license(value: str) -> str | None:
    return {
        "any": None,
        "share": "f",
        "commercial": "fc",
        "modify": "fm",
        "commercial-modify": "fmc",
        "creative-commons": "cl",
        "commercial-other": "ol",
    }[value]


def ddgs_license(value: str) -> str | None:
    if value == "commercial-other":
        raise SkillError("DDGS has no equivalent for the SerpApi 'commercial-other' license filter")
    return {
        "any": None,
        "share": "Share",
        "commercial": "ShareCommercially",
        "modify": "Modify",
        "commercial-modify": "ModifyCommercially",
        "creative-commons": "any",
        "commercial-other": None,
    }[value]


def serpapi_orientation(value: str) -> str | None:
    return {"any": None, "square": "s", "tall": "t", "wide": "w"}[value]


def serpapi_size(value: str) -> str | None:
    return {"any": None, "small": "i", "medium": "m", "large": "l", "wallpaper": "xga"}[value]


def serpapi_time_limit(value: str) -> str | None:
    return {"any": None, "d": "d", "w": "w", "m": "m", "y": "y"}[value]


def serpapi_type(value: str) -> tuple[str | None, str | None]:
    if value == "transparent":
        return None, "trans"
    return ({"any": None, "photo": "photo", "clipart": "clipart", "lineart": "lineart", "animated": "animated"}[value], None)


def ddgs_type(value: str) -> str | None:
    return {"any": None, "photo": "photo", "clipart": "clipart", "lineart": "line", "transparent": "transparent", "animated": "gif"}[value]


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
        provider=f"ddgs-{str(item.get('source') or 'auto').lower()}",
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


def create_session() -> Any:
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except ImportError as exc:
        raise SkillError("Missing requests. Install it with: py -3 -m pip install --user requests") from exc
    retry = Retry(
        total=1,
        connect=1,
        read=0,
        status=0,
        backoff_factor=0.4,
        status_forcelist=(),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    session = requests.Session()
    session.trust_env = os.environ.get("WEBSITE_IMAGE_FINDER_TRUST_ENV", "").strip() == "1"
    session.headers.update({"User-Agent": USER_AGENT})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def search_serpapi(
    session: Any,
    query: str,
    api_key: str,
    max_results: int,
    region: str,
    page: int,
    orientation: str,
    image_type: str,
    license_filter: str,
    safe_search: str,
    size: str,
    color: str,
    time_limit: str,
) -> list[Candidate]:
    gl, hl = region_to_google(region)
    image_type_value, color_value = serpapi_type(image_type)
    params: dict[str, Any] = {
        "engine": "google_images",
        "q": query,
        "api_key": api_key,
        "gl": gl,
        "hl": hl,
        "ijn": max(page - 1, 0),
        "safe": "active" if safe_search != "off" else "off",
        "device": "desktop",
        "output": "json",
    }
    if orientation_value := serpapi_orientation(orientation):
        params["imgar"] = orientation_value
    if image_type_value:
        params["image_type"] = image_type_value
    if color_value:
        params["image_color"] = color_value
    elif color != "any":
        params["image_color"] = color
    if license_value := serpapi_license(license_filter):
        params["licenses"] = license_value
    if size_value := serpapi_size(size):
        params["imgsz"] = size_value
    if period_unit := serpapi_time_limit(time_limit):
        params["period_unit"] = period_unit

    response = session.get(SERPAPI_ENDPOINT, params=params, timeout=(10, 35))
    try:
        payload = response.json()
    except ValueError as exc:
        raise SkillError(f"SerpApi returned HTTP {response.status_code} with non-JSON content") from exc
    if response.status_code >= 400:
        message = payload.get("error") if isinstance(payload, dict) else None
        raise SkillError(f"SerpApi HTTP {response.status_code}: {message or 'request failed'}")
    if payload.get("error"):
        raise SkillError(f"SerpApi: {payload['error']}")

    output: list[Candidate] = []
    for position, item in enumerate(payload.get("images_results", [])[:max_results], 1):
        candidate = make_candidate("serpapi", query, position, item)
        if candidate:
            output.append(candidate)
    return output


def search_ddgs(
    query: str,
    max_results: int,
    region: str,
    page: int,
    backend: str,
    orientation: str,
    image_type: str,
    license_filter: str,
    safe_search: str,
    size: str,
    color: str,
    time_limit: str,
) -> list[Candidate]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise SkillError("Missing ddgs. Install it with: py -3 -m pip install --user ddgs") from exc

    kwargs: dict[str, Any] = {
        "query": query,
        "region": region,
        "safesearch": {"active": "on", "moderate": "moderate", "off": "off"}[safe_search],
        "max_results": max_results,
        "page": page,
        "backend": backend,
    }
    if orientation != "any":
        kwargs["layout"] = {"square": "Square", "tall": "Tall", "wide": "Wide"}[orientation]
    if type_value := ddgs_type(image_type):
        kwargs["type_image"] = type_value
    if license_value := ddgs_license(license_filter):
        kwargs["license_image"] = license_value
    if size != "any":
        kwargs["size"] = size.capitalize()
    if color != "any":
        kwargs["color"] = color.capitalize() if color != "bw" else "Monochrome"
    if time_limit != "any":
        kwargs["timelimit"] = time_limit

    raw = DDGS(timeout=20).images(**kwargs)
    output: list[Candidate] = []
    for position, item in enumerate(raw, 1):
        candidate = make_candidate("ddgs", query, position, item)
        if candidate:
            output.append(candidate)
    return output


def score_candidate(candidate: Candidate, preferred_domains: list[str], orientation: str) -> float:
    score = max(0.0, 100.0 - min( candidate.provider_position, 100))
    title_words = unicode_words(candidate.title)
    query_words = set().union(*(unicode_words(query) for query in candidate.queries))
    score += 5.0 * len(title_words & query_words)

    if candidate.reported_width and candidate.reported_height:
        pixels = candidate.reported_width * candidate.reported_height
        score += min(30.0, max(0.0, math.log2(max(pixels, 1) / 250_000 + 1) * 7.5))
        ratio = candidate.reported_width / candidate.reported_height
        if orientation == "wide" and ratio >= 1.25:
            score += 8
        elif orientation == "tall" and ratio <= 0.8:
            score += 8
        elif orientation == "square" and 0.85 <= ratio <= 1.18:
            score += 8

    if any(host_matches(candidate.source_page_url, [domain]) or host_matches(candidate.image_url, [domain]) for domain in preferred_domains):
        score += 75.0
    if candidate.license_url:
        score += 8.0
    if not candidate.source_page_url:
        score -= 12.0
    suspicious = f"{candidate.title} {candidate.image_url}".casefold()
    if any(word in suspicious for word in ("thumbnail", "thumb", "watermark", "preview")):
        score -= 8.0
    return round(score, 3.0)


def merge_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        key = canonical_url(candidate.image_url)
        current = merged.get(key)
        if current is None:
            merged[key] = candidate
            continue
        for query in candidate.queries:
            if query not in current.queries:
                current.queries.append(query)
        if candidate.score > current.score:
            candidate.queries = current.queries
            merged[key] = candidate
    return list(merged.values())
