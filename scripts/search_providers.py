"""Free and explicitly selected paid image-provider adapters.

Importing this module makes no remote calls. Providers' own limitations remain
explicit, and SerpApi stays opt-in by the main CLI.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Iterable

from candidate_model import (
    Candidate, DdgsSearchBatch, int_or_none, make_candidate,
    make_openverse_candidate, safe_result_url,
)
from common import SkillError, canonical_url, domain_of
from safe_transport import mount_pinned_transport

USER_AGENT = "WebsiteImageFinder/0.5.2 (https://github.com/Bl0ck154/website-image-finder-skill)"
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
OPENVERSE_ENDPOINT = "https://api.openverse.org/v1/images/"
WIKIMEDIA_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
DDGS_SOURCE_NAMES = {"bing": "Bing", "duckduckgo": "DuckDuckGo"}

def installed_ddgs_version() -> str | None:
    try:
        return package_version("ddgs")
    except PackageNotFoundError:
        return None


def canonical_ddgs_source(value: Any) -> str | None:
    normalized = re.sub(r"[^a-z]", "", str(value or "").casefold())
    if normalized.startswith("duckduckgo"):
        return "DuckDuckGo"
    if normalized.startswith("bing"):
        return "Bing"
    return None


def detect_ddgs_actual_sources(client: Any, raw_results: list[dict[str, Any]]) -> list[str]:
    """Report the engines DDGS actually instantiated; use result source only as a compatibility fallback."""
    engine_sources: list[str] = []
    engine_cache = getattr(client, "_engines_cache", None)
    if isinstance(engine_cache, dict):
        for engine in engine_cache.values():
            source = canonical_ddgs_source(getattr(engine, "name", None) or type(engine).__name__)
            if source and source not in engine_sources:
                engine_sources.append(source)
    if engine_sources:
        return engine_sources

    result_sources: list[str] = []
    for item in raw_results:
        source = canonical_ddgs_source(item.get("source"))
        if source and source not in result_sources:
            result_sources.append(source)
    return result_sources or ["Unknown"]


def merge_unique(target: list[str], values: Iterable[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def ddgs_backend_mismatch_error(requested_backend: str, ddgs_version: str | None, actual_sources: list[str]) -> str | None:
    if requested_backend == "auto" or not actual_sources:
        return None
    expected = DDGS_SOURCE_NAMES[requested_backend]
    if actual_sources == [expected]:
        return None
    actual = ", ".join(actual_sources)
    return (
        f"Requested DDGS backend '{requested_backend}', but DDGS {ddgs_version or 'unknown'} returned\n"
        f"{actual} results. This DDGS version does not provide a working\n"
        f"{expected} Images backend."
    )

def region_to_google(region: str) -> tuple[str | None, str | None]:
    normalized = region.strip().lower().replace("_", "-")
    if normalized == "auto":
        return None, None
    match = re.fullmatch(r"([a-z]{2})-([a-z]{2,3})", normalized)
    if not match:
        raise SkillError("region must be auto or look like lt-lt, ua-uk, or us-en")
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
    if value == "creative-commons":
        raise SkillError("DDGS cannot guarantee a Creative Commons license filter; use --provider openverse")
    if value == "commercial-other":
        raise SkillError("DDGS has no equivalent for the SerpApi 'commercial-other' license filter")
    return {
        "any": None,
        "share": "Share",
        "commercial": "ShareCommercially",
        "modify": "Modify",
        "commercial-modify": "ModifyCommercially",
        "creative-commons": None,
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

def create_session() -> Any:
    try:
        import requests
    except ImportError as exc:
        raise SkillError("Missing requests. Install it with: py -3 -m pip install --user requests") from exc
    session = requests.Session()
    session.trust_env = os.environ.get("WEBSITE_IMAGE_FINDER_TRUST_ENV", "").strip() == "1"
    session.headers.update({"User-Agent": USER_AGENT})
    mount_pinned_transport(session)
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
        "ijn": max(page - 1, 0),
        "safe": "active" if safe_search != "off" else "off",
        "device": "desktop",
        "output": "json",
    }
    if gl:
        params["gl"] = gl
    if hl:
        params["hl"] = hl
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
) -> DdgsSearchBatch:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise SkillError("Missing ddgs. Install it with: py -3 -m pip install --user ddgs") from exc

    kwargs: dict[str, Any] = {
        "query": query,
        "region": "wt-wt" if region == "auto" else region,
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

    client = DDGS(timeout=20)
    raw = client.images(**kwargs)
    actual_sources = detect_ddgs_actual_sources(client, raw)
    output: list[Candidate] = []
    for position, item in enumerate(raw, 1):
        candidate = make_candidate("ddgs", query, position, item)
        if candidate:
            output.append(candidate)
    return DdgsSearchBatch(
        candidates=output,
        ddgs_version=installed_ddgs_version() or "unknown",
        requested_backend=backend,
        actual_sources=actual_sources,
    )


def search_openverse(
    session: Any,
    query: str,
    max_results: int,
    page: int,
    orientation: str,
    image_type: str,
    license_filter: str,
    safe_search: str,
    size: str,
    color: str,
    time_limit: str,
) -> list[Candidate]:
    """Search Openverse public media index without an API key.

    Openverse results carry license metadata, but users must still verify rights.
    Unsupported filters fail explicitly instead of silently being ignored.
    """
    if image_type != "any":
        raise SkillError("Openverse does not support --image-type; use --image-type any")
    if color != "any" or time_limit != "any":
        raise SkillError("Openverse does not support --color or --time-limit filters")
    if size not in {"any", "small", "medium", "large"}:
        raise SkillError("Openverse supports --size any|small|medium|large")
    if license_filter in {"share", "commercial-other"}:
        raise SkillError(f"Openverse does not support --license {license_filter}")

    params: dict[str, Any] = {
        "q": query,
        "page": page,
        "page_size": min(max_results, 100),
        "mature": "true" if safe_search == "off" else "false",
    }
    if orientation != "any":
        params["aspect_ratio"] = {"wide": "wide", "tall": "tall", "square": "square"}[orientation]
    if size != "any":
        params["size"] = size
    license_types = {
        "any": None,
        "creative-commons": "all-cc",
        "commercial": "commercial",
        "modify": "modification",
        "commercial-modify": "commercial,modification",
    }
    if value := license_types[license_filter]:
        params["license_type"] = value

    response = session.get(OPENVERSE_ENDPOINT, params=params, timeout=(6, 15))
    try:
        payload = response.json()
    except ValueError as exc:
        raise SkillError(f"Openverse HTTP {response.status_code}: non-JSON response") from exc
    if response.status_code >= 400:
        raise SkillError(f"Openverse HTTP {response.status_code}: search unavailable")
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SkillError("Openverse returned unexpected search payload")
    result: list[Candidate] = []
    for position, item in enumerate(payload["results"][:max_results], 1):
        if not isinstance(item, dict):
            continue
        candidate = make_openverse_candidate(query, position, item)
        if candidate:
            result.append(candidate)
    return result


def search_wikimedia(
    session: Any, query: str, max_results: int, page: int,
    orientation: str, image_type: str, license_filter: str,
    safe_search: str, size: str, color: str, time_limit: str,
) -> list[Candidate]:
    """Keyless Wikimedia Commons fallback. Local selection and manual license review are required."""
    if license_filter != "any":
        raise SkillError("Wikimedia fallback does not guarantee requested license filters; use Openverse")
    if image_type not in {"any", "photo"} or color != "any" or time_limit != "any":
        raise SkillError("Wikimedia fallback does not support image type, color or time filters")
    if size not in {"any", "small", "medium", "large"}:
        raise SkillError("Wikimedia fallback cannot honor the requested size filter")
    limit = min(max_results, 25)
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "gsroffset": (page - 1) * limit,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
    }
    response = session.get(WIKIMEDIA_ENDPOINT, params=params, timeout=(6, 18))
    try:
        payload = response.json()
    except ValueError as exc:
        raise SkillError(f"Wikimedia HTTP {response.status_code}: non-JSON response") from exc
    if response.status_code >= 400 or not isinstance(payload, dict) or payload.get("error"):
        raise SkillError(f"Wikimedia HTTP {response.status_code}: search unavailable")
    pages = payload.get("query", {}).get("pages", [])
    if not isinstance(pages, list):
        raise SkillError("Wikimedia returned unexpected search payload")
    results: list[Candidate] = []
    for item in sorted(pages, key=lambda value: value.get("index", 100000)):
        details = item.get("imageinfo", [])
        if not details or not isinstance(details[0], dict):
            continue
        info = details[0]
        mime = str(info.get("mime") or "").lower()
        if not mime.startswith("image/") or mime in {"image/svg+xml", "image/vnd.djvu"}:
            continue
        try:
            image_url = safe_result_url(info.get("url"), required=True)
        except SkillError:
            continue
        width = int_or_none(info.get("width"))
        height = int_or_none(info.get("height"))
        if width and height:
            ratio = width / max(height, 1)
            if ((orientation == "wide" and ratio < 1.25) or
                (orientation == "tall" and ratio > 0.8) or
                (orientation == "square" and not 0.85 <= ratio <= 1.18)):
                continue
        if size == "large" and (not width or width < 1200):
            continue
        metadata = info.get("extmetadata") or {}
        def meta(key: str) -> str:
            value = metadata.get(key) or {}
            return str(value.get("value") or "").strip() if isinstance(value, dict) else ""
        page_url = safe_result_url(info.get("descriptionurl"))
        license_url = safe_result_url(meta("LicenseUrl")) or None
        title = str(item.get("title") or "").removeprefix("File:").strip()
        key = hashlib.sha1(canonical_url(image_url).encode("utf-8", "replace")).hexdigest()[:12]
        results.append(Candidate(
            id=f"img-{key}", rank=len(results) + 1, provider="wikimedia-commons",
            provider_position=len(results) + 1, queries=[query], title=title,
            image_url=image_url, thumbnail_url="", source_page_url=page_url,
            source_domain=domain_of(page_url), source_label="Wikimedia Commons",
            reported_width=width, reported_height=height,
            license_url=license_url, license_tag=meta("LicenseShortName") or None,
        ))
    return results

def provider_order(requested: str, license_filter: str, no_fallback: bool, *, ddgs_available: bool | None = None) -> list[str]:
    """Explicit paid providers are opt-in; automatic search never uses paid APIs."""
    if requested != "auto":
        return [requested]
    # License-restricted queries must not silently fall through to unverified licenses.
    if license_filter in {"creative-commons", "commercial", "modify", "commercial-modify"}:
        return ["openverse"]
    if ddgs_available is None:
        ddgs_available = importlib.util.find_spec("ddgs") is not None
    chain = ["ddgs", "openverse", "wikimedia"] if ddgs_available else ["openverse", "wikimedia"]
    return chain[:1] if no_fallback else chain
