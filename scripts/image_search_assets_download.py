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



from image_search_core import *

def dhash_image(image: Any, size: int = 8) -> str:
    from PIL import Image, ImageOps

    rgba = image.convert("RGBA")
    background_rgba = Image.new("RGBA", rgba.size, "white")
    background_rgba.alpha_composite(rgba)
    gray = ImageOps.grayscale(background_rgba.convert("RGB"))
    background = gray.resize((size + 1, size))
    if hasattr(background, "get_flattened_data"):
        pixels = list(background.get_flattened_data())
    else:
        pixels = list(background.getdata())
    value = 0
    for row in range(size):
        offset = row * (size + 1)
        for col in range(size):
            value = (value << 1) | int(pixels[offset + col] > pixels[offset + col + 1])
    return f"{value:0{size * size // 4}x}"


def hamming_hex(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def request_with_safe_redirects(session: Any, url: str, headers: dict[str, str]) -> Any:
    current = validate_public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        response = session.get(current, headers=headers, timeout=(10, 30), stream=True, allow_redirects=False)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise SkillError("redirect response has no Location header")
            current = safe_redirect(current, location)
            continue
        return response
    raise SkillError(f"too many redirects (>{MAX_REDIRECTS})")


def image_mode_with_alpha(image: Any) -> tuple[str, bool]:
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    return ("RGBA" if has_alpha else "RGB", has_alpha)


def download_candidate(
    session: Any,
    candidate: Candidate,
    out_dir: Path,
    min_width: int,
    min_height: int,
    max_bytes: int,
    max_pixels: int,
    seen_sha: set[str],
    seen_hashes: list[str],
    near_duplicate_distance: int,
    allow_first_frame: bool,
) -> None:
    try:
        from PIL import Image, ImageOps, features
    except ImportError as exc:
        raise SkillError("Missing Pillow. Install it with: py -3 -m pip install --user Pillow") from exc

    if candidate.reported_width and candidate.reported_height:
        if candidate.reported_width < min_width or candidate.reported_height < min_height:
            candidate.status = "skipped-metadata-small"
            candidate.error = f"reported {candidate.reported_width}x{candidate.reported_height} below minimum {min_width}x{min_height}"
            return

    if not features.check("webp"):
        candidate.status = "failed"
        candidate.error = "Pillow has no WebP support"
        return

    headers = {"Accept": "image/avif,image/webp,image/apng,image/png,image/jpeg,image/gif,image/*;q=0.8,*/*;q=0.1"}
    if referer := origin_referer(candidate.source_page_url):
        headers["Referer"] = referer

    response = None
    try:
        response = request_with_safe_redirects(session, candidate.image_url, headers)
        if response.status_code >= 400:
            raise SkillError(f"HTTP {response.status_code}")
        candidate.downloaded_url = validate_public_url(response.url)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        candidate.content_type = content_type or None
        if content_type in {"image/svg+xml", "text/html", "application/xhtml+xml"} or content_type.startswith("text/"):
            raise SkillError(f"unsupported content type: {content_type or 'missing'}")
        content_length = int_or_none(response.headers.get("content-length"))
        if content_length is not None and content_length > max_bytes:
            raise SkillError(f"image exceeds {max_bytes // (1024 * 1024)} MB")

        data = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            data.extend(chunk)
            if len(data) > max_bytes:
                raise SkillError(f"image exceeds {max_bytes // (1024 * 1024)} MB")
        if not data:
            raise SkillError("empty response")
        if bytes(data[:64]).lstrip().lower().startswith((b"<!doctype html", b"<html", b"<?xml")):
            raise SkillError("response appears to be HTML/XML, not a raster image")

        source_data = bytes(data)
        candidate.source_bytes = len(source_data)
        digest = hashlib.sha256(source_data).hexdigest()
        candidate.sha256 = digest
        if digest in seen_sha:
            candidate.status = "duplicate"
            candidate.error = "exact duplicate"
            return

        Image.MAX_IMAGE_PIXELS = max_pixels
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(source_data)) as probe:
                probe.verify()
            with Image.open(BytesIO(source_data)) as opened:
                if getattr(opened, "is_animated", False) and getattr(opened, "n_frames", 1) > 1:
                    if not allow_first_frame:
                        raise SkillError("animated images are rejected by default; use --allow-first-frame to flatten frame 0")
                    opened.seek(0)
                    candidate.notes.append("flattened first frame of animated image")
                opened.load()
                image = ImageOps.exif_transpose(opened)
                width, height = image.size
                if width * height > max_pixels:
                    raise SkillError(f"image exceeds maximum pixel count: {width}x{height}")
                candidate.actual_width = width
                candidate.actual_height = height
                if width < min_width or height < min_height:
                    candidate.status = "skipped-small"
                    candidate.error = f"{width}x{height} below minimum {min_width}x{min_height}"
                    return
                mode, has_alpha = image_mode_with_alpha(image)
                candidate.has_alpha = has_alpha
                normalized = image.convert(mode)
                dhash = dhash_image(normalized)
                candidate.dhash = dhash
                if any(hamming_hex(dhash, prior) <= near_duplicate_distance for prior in seen_hashes if prior):
                    candidate.status = "duplicate"
                    candidate.error = "near duplicate"
                    return

                filename = f"{candidate.rank:03d}-{slugify(candidate.title)}-{digest[:8]}.webp"
                target = out_dir / filename
                fd, temp_name = tempfile.mkstemp(prefix=".candidate-", suffix=".webp", dir=out_dir)
                os.close(fd)
                try:
                    normalized.save(temp_name, "WEBP", quality=88, method=6, exact=has_alpha)
                    os.replace(temp_name, target)
                finally:
                    try:
                        os.unlink(temp_name)
                    except FileNotFoundError:
                        pass

        seen_sha.add(digest)
        seen_hashes.append(candidate.dhash or "")
        candidate.local_file = filename
        candidate.status = "downloaded"
        candidate.error = None
    except (SkillError, OSError, ValueError) as exc:
        candidate.status = "failed"
        candidate.error = redact(str(exc))[:500]
    except Exception as exc:
        candidate.status = "failed"
        candidate.error = redact(f"{type(exc).__name__}: {exc}")[:500]
    finally:
        if response is not None:
            response.close()


def next_batch_number(candidates: Iterable[Candidate]) -> int:
    return max((candidate.batch or 0 for candidate in candidates), default=0) + 1


def download_next_batch(
    session: Any,
    candidates: list[Candidate],
    out_dir: Path,
    settings: dict[str, Any],
    count: int,
    max_attempts: int,
    *,
    retry_failed: bool = False,
) -> tuple[list[Candidate], int]:
    seen_sha = {candidate.sha256 for candidate in candidates if candidate.sha256 and candidate.status == "downloaded"}
    seen_hashes = [candidate.dhash for candidate in candidates if candidate.dhash and candidate.status == "downloaded"]
    batch_number = next_batch_number(candidates)
    downloaded: list[Candidate] = []
    attempts = 0
    retryable = {"found"}
    if retry_failed:
        retryable.add("failed")

    for candidate in candidates:
        if len(downloaded) >= count or attempts >= max_attempts:
            break
        if candidate.status not in retryable:
            continue
        if retry_failed and candidate.status != "found":
            candidate.status = "found"
            candidate.error = None
        before = candidate.status
        download_candidate(
            session,
            candidate,
            out_dir,
            int(settings["min_width"]),
            int(settings["min_height"]),
            int(settings["max_mb"]) * 1024 * 1024,
            int(settings["max_pixels"]),
            seen_sha,
            seen_hashes,
            int(settings["near_duplicate_distance"]),
            bool(settings["allow_first_frame"]),
        )
        if before == "found" and candidate.status != "skipped-metadata-small":
            attempts += 1
        if candidate.status == "downloaded":
            candidate.batch = batch_number
            downloaded.append(candidate)

    return downloaded, attempts
