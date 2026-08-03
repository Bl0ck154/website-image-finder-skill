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
from image_search_assets_download import *

def checkerboard(size: tuple[int, int], square: int = 18) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, "#eeeeee")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], square):
        for x in range(0, size[0], square):
            if (x // square + y // square) % 2:
                draw.rectangle((x, y, min(x + square - 1, size[0] - 1), min(y + square - 1, size[1] - 1)), fill="#d8d8d8")
    return image


def prepare_preview(path: Path) -> Any:
    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        opened.load()
        image = ImageOps.exif_transpose(opened)
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        if not has_alpha:
            return image.convert("RGB")
        rgba = image.convert("RGBA")
        background = checkerboard(rgba.size).convert("RGBA")
        background.alpha_composite(rgba)
        return background.convert("RGB")


def plan_justified_rows(
    items: list[tuple[Candidate, Any]],
    width: int,
    margin: int,
    gap: int,
    target_height: int,
    max_last_height: int,
) -> list[tuple[list[tuple[Candidate, Any]], int, bool]]:
    available = width - margin * 2
    rows: list[tuple[list[tuple[Candidate, Any]], int, bool]] = []
    current: list[tuple[Candidate, Any]] = []
    ratio_sum = 0.0

    for item in items:
        image = item[1]
        ratio = max(0.05, image.width / max(image.height, 1))
        current.append(item)
        ratio_sum += ratio
        projected = target_height * ratio_sum + gap * (len(current) - 1)
        if projected >= available or len(current) >= 5:
            height = max(1, int((available - gap * (len(current) - 1)) / ratio_sum))
            rows.append((current, height, True))
            current = []
            ratio_sum = 0.0

    if current:
        fill_height = int((available - gap * (len(current) - 1)) / max(ratio_sum, 0.05))
        if len(current) > 1 and fill_height <= max_last_height:
            rows.append((current, max(1, fill_height), True))
        else:
            rows.append((current, target_height, False))
    return rows


def create_contact_sheet(batch_candidates: list[Candidate], out_dir: Path, batch_number: int) -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    items: list[tuple[Candidate, Any]] = []
    for candidate in batch_candidates:
        if not candidate.local_file:
            continue
        path = out_dir / candidate.local_file
        if not path.is_file():
            continue
        try:
            items.append((candidate, prepare_preview(path)))
        except Exception:
            continue
    if not items:
        return None

    sheet_width = 1600
    margin = 8
    gap = 8
    target_height = 260
    rows = plan_justified_rows(items, sheet_width, margin, gap, target_height, 340)
    sheet_height = margin * 2 + sum(row[1] for row in rows) + gap * max(0, len(rows) - 1)
    sheet = Image.new("RGB", (sheet_width, sheet_height), "#202020")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    y = margin

    for row_items, row_height, justified in rows:
        ratios = [image.width / max(image.height, 1) for _, image in row_items]
        if justified:
            available = sheet_width - margin * 2 - gap * (len(row_items) - 1)
            widths = [max(1, int(row_height * ratio)) for ratio in ratios]
            difference = available - sum(widths)
            widths[-1] += difference
        else:
            widths = [max(1, int(row_height * ratio)) for ratio in ratios]
        row_width = sum(widths) + gap * (len(widths) - 1)
        x = margin if justified else margin + max(0, (sheet_width - margin * 2 - row_width) // 2)

        for (candidate, image), tile_width in zip(row_items, widths):
            resized = image.resize((tile_width, row_height), Image.Resampling.LANCZOS)
            sheet.paste(resized, (x, y))
            label_h = min(32, max(22, row_height // 8))
            draw.rectangle((x, y + row_height - label_h, x + tile_width - 1, y + row_height - 1), fill="#111111")
            domain = candidate.source_domain or candidate.source_label or "unknown source"
            dims = f"{candidate.actual_width or '?'}x{candidate.actual_height or '?'}"
            label = f"#{candidate.rank} | {dims} | {domain}"
            approx_chars = max(8, tile_width // 7)
            draw.text((x + 6, y + row_height - label_h + 8), label[:approx_chars], fill="white", font=font)
            x += tile_width + gap
        y += row_height + gap

    output_name = f"contact-sheet-{batch_number:02d}.jpg"
    output = out_dir / output_name
    fd, temp_name = tempfile.mkstemp(prefix=".contact-sheet-", suffix=".jpg", dir=out_dir)
    os.close(fd)
    try:
        sheet.save(temp_name, "JPEG", quality=90, optimize=True, progressive=True)
        os.replace(temp_name, output)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return output_name


def compact_candidate(candidate: Candidate) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": candidate.id,
        "rank": candidate.rank,
        "file": candidate.local_file,
        "image_url": candidate.image_url,
        "source_url": candidate.source_page_url,
        "source_domain": candidate.source_domain,
        "width": candidate.actual_width,
        "height": candidate.actual_height,
    }
    if candidate.license_url:
        payload["license_url"] = candidate.license_url
    if candidate.license_tag:
        payload["license_tag"] = candidate.license_tag
    return payload


def url_candidate(candidate: Candidate) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": candidate.id,
        "rank": candidate.rank,
        "image_url": candidate.image_url,
        "source_url": candidate.source_page_url,
        "source_domain": candidate.source_domain,
        "width": candidate.reported_width,
        "height": candidate.reported_height,
    }
    if candidate.license_url:
        payload["license_url"] = candidate.license_url
    if candidate.license_tag:
        payload["license_tag"] = candidate.license_tag
    return payload


def write_batch_outputs(batch_candidates: list[Candidate], out_dir: Path, batch_number: int) -> tuple[str | None, str]:
    sheet = create_contact_sheet(batch_candidates, out_dir, batch_number)
    filename = f"candidates-{batch_number:02d}.json"
    payload = {
        "schema_version": 1,
        "batch": batch_number,
        "created_at": now_iso(),
        "contact_sheet": sheet,
        "count": len(batch_candidates),
        "candidates": [compact_candidate(candidate) for candidate in batch_candidates],
        "rights_notice": "Verify the source page and license before publication; search metadata is not legal proof of permission.",
    }
    atomic_write_json(out_dir / filename, payload)
    return sheet, filename


def write_urls(candidates: list[Candidate], out_dir: Path) -> str:
    filename = "urls.json"
    atomic_write_json(
        out_dir / filename,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "count": len(candidates),
            "results": [url_candidate(candidate) for candidate in candidates],
            "rights_notice": "Verify the source page and license before publication; search metadata is not legal proof of permission.",
        },
    )
    return filename


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
