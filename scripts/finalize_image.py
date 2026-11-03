#!/usr/bin/env python3
"""Convert a selected candidate into an optimized local website asset with optional source sidecar."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import warnings
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import VERSION, SkillError, atomic_write_json, ensure_within_root, resolve_under_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Input raster image path")
    source.add_argument("--cache", "--manifest", dest="cache", help="Search results cache; combine with --candidate")
    parser.add_argument("--candidate", help="Candidate id or numeric rank when --cache is used")
    parser.add_argument("--root", default=".", help="Project root; input/output must stay inside it")
    parser.add_argument("--output", required=True, help="Output .webp, .jpg/.jpeg, or .png path")
    parser.add_argument("--max-width", type=int, default=1800)
    parser.add_argument("--max-height", type=int, default=1800)
    parser.add_argument("--max-pixels", type=int, default=30_000_000)
    parser.add_argument("--max-input-mb", type=int, default=40, help="Reject local inputs larger than this")
    parser.add_argument("--quality", type=int, default=84)
    parser.add_argument("--jpeg-background", default="#ffffff", help="Background used when flattening alpha to JPEG")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-first-frame", action="store_true")
    parser.add_argument("--no-sidecar", action="store_true", help="Do not write private provenance metadata when using a search cache")
    return parser.parse_args()


def find_candidate(payload: dict[str, Any], selector: str) -> dict[str, Any]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise SkillError("search cache results must be a list")
    for candidate in results:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("id")) == selector or str(candidate.get("rank")) == selector:
            return candidate
    raise SkillError(f"candidate not found in search cache: {selector}")


def resolve_source(args: argparse.Namespace, root: Path) -> tuple[Path, dict[str, Any] | None, Path | None]:
    if args.input:
        source = resolve_under_root(args.input, root, label="input")
        return source, None, None
    if not args.candidate:
        raise SkillError("--candidate is required with --cache")
    manifest_path = resolve_under_root(str(args.cache), root, label="search cache")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillError(f"cannot read search cache: {manifest_path}") from exc
    candidate = find_candidate(payload, str(args.candidate))
    local_file = candidate.get("local_file")
    if not local_file or candidate.get("status") != "downloaded":
        raise SkillError("selected candidate has no downloaded local file")
    source = ensure_within_root(manifest_path.parent / str(local_file), root, label="candidate file")
    return source, candidate, manifest_path


def main() -> int:
    args = parse_args()
    try:
        if args.max_width < 1 or args.max_height < 1 or not 1 <= args.quality <= 100:
            raise SkillError("invalid size or quality")
        if args.max_pixels < 1_000_000 or args.max_pixels > 200_000_000:
            raise SkillError("--max-pixels must be between 1,000,000 and 200,000,000")
        if args.max_input_mb < 1 or args.max_input_mb > 1000:
            raise SkillError("--max-input-mb must be between 1 and 1000")
        try:
            from PIL import Image, ImageColor, ImageOps, UnidentifiedImageError, features
        except ImportError as exc:
            raise SkillError("Missing Pillow. Install it with: py -3 -m pip install --user Pillow") from exc

        root = Path(args.root).resolve()
        if not root.is_dir():
            raise SkillError(f"project root does not exist: {root}")
        source, candidate, manifest_path = resolve_source(args, root)
        target = resolve_under_root(args.output, root, label="output")
        if not source.is_file():
            raise SkillError(f"input not found: {source}")
        if source.stat().st_size > args.max_input_mb * 1024 * 1024:
            raise SkillError(f"input exceeds {args.max_input_mb} MB")
        if source.resolve() == target.resolve(strict=False):
            raise SkillError("input and output must be different files")
        if target.exists() and not args.overwrite:
            raise SkillError(f"output exists: {target}; use --overwrite to replace it")
        ext = target.suffix.lower()
        if ext not in {".webp", ".jpg", ".jpeg", ".png"}:
            raise SkillError("output extension must be .webp, .jpg/.jpeg, or .png")
        if ext == ".webp" and not features.check("webp"):
            raise SkillError("Pillow build has no WebP support")

        target.parent.mkdir(parents=True, exist_ok=True)
        Image.MAX_IMAGE_PIXELS = args.max_pixels
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as opened:
                if getattr(opened, "is_animated", False) and getattr(opened, "n_frames", 1) > 1:
                    if not args.allow_first_frame:
                        raise SkillError("animated images are rejected by default; use --allow-first-frame to flatten frame 0")
                    opened.seek(0)
                opened.load()
                image = ImageOps.exif_transpose(opened)
                if image.width * image.height > args.max_pixels:
                    raise SkillError("image exceeds maximum pixel count")
                image.thumbnail((args.max_width, args.max_height), Image.Resampling.LANCZOS)
                has_alpha = "A" in image.getbands() or "transparency" in image.info

                fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=target.suffix, dir=target.parent)
                os.close(fd)
                try:
                    if ext == ".webp":
                        mode = "RGBA" if has_alpha else "RGB"
                        image.convert(mode).save(temp_name, "WEBP", quality=args.quality, method=6, exact=has_alpha)
                    elif ext in {".jpg", ".jpeg"}:
                        if has_alpha:
                            background = Image.new("RGB", image.size, ImageColor.getrgb(args.jpeg_background))
                            rgba = image.convert("RGBA")
                            background.paste(rgba, mask=rgba.getchannel("A"))
                            normalized = background
                        else:
                            normalized = image.convert("RGB")
                        normalized.save(temp_name, "JPEG", quality=args.quality, optimize=True, progressive=True)
                    else:
                        mode = "RGBA" if has_alpha else "RGB"
                        image.convert(mode).save(temp_name, "PNG", optimize=True)
                    os.replace(temp_name, target)
                finally:
                    try:
                        os.unlink(temp_name)
                    except FileNotFoundError:
                        pass

        with Image.open(target) as check:
            check.verify()
        if candidate is not None and manifest_path is not None and not args.no_sidecar:
            # Keep source URLs and possible signed image links out of deployed public assets.
            # The project-local .image-search directory must be gitignored.
            sidecar = resolve_under_root(
                Path(".image-search") / "provenance" / (str(target.relative_to(root)) + ".source.json"),
                root,
                label="private source metadata",
            )
            sidecar_payload = {
                "schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tool": "website-image-finder",
                "tool_version": VERSION,
                "asset": str(target.relative_to(root)).replace("\\", "/"),
                "candidate_id": candidate.get("id"),
                "candidate_rank": candidate.get("rank"),
                "title": candidate.get("title"),
                "image_url": candidate.get("image_url"),
                "downloaded_url": candidate.get("downloaded_url"),
                "source_page_url": candidate.get("source_page_url"),
                "source_domain": candidate.get("source_domain"),
                "license_url": candidate.get("license_url"),
                "license_tag": candidate.get("license_tag"),
                "source_sha256": candidate.get("sha256"),
                "rights_notice": "Verify the source page and license before publication; search metadata is not legal proof of permission.",
            }
            atomic_write_json(sidecar, sidecar_payload)
            print(f"Source sidecar: {sidecar}")
        print(f"Saved: {target}")
        print(f"Size: {target.stat().st_size} bytes")
        return 0
    except (SkillError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # defensive decoder boundary
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
