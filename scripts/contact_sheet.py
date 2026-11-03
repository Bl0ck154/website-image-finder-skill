"""Build the justified contact sheet shown to an agent for image selection."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from candidate_model import Candidate

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
