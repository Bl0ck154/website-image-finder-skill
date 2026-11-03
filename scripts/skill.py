#!/usr/bin/env python3
"""Small launcher for Website Image Finder using the current Python installation."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
COMMANDS = {
    "search": SCRIPTS_DIR / "image_search.py",
    "more": SCRIPTS_DIR / "download_more.py",
    "finalize": SCRIPTS_DIR / "finalize_image.py",
}


def check() -> int:
    modules = (
        ("requests", "requests"),
        ("PIL", "Pillow"),
        ("ddgs", "ddgs (optional when SerpApi is configured)"),
    )
    missing_required: list[str] = []
    for module, label in modules:
        present = importlib.util.find_spec(module) is not None
        print(f"{'OK' if present else 'MISSING'}: {label}")
        if not present and module in {"requests", "PIL"}:
            missing_required.append(label)
    has_key = bool((os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERPAPI_KEY") or "").strip())
    print(f"{'OK' if has_key else 'INFO'}: SerpApi key {'is configured' if has_key else 'is not configured'}")
    if importlib.util.find_spec("ddgs") is None and not has_key:
        print("INFO: DDGS unavailable; Openverse can still search without an API key")
    if "Pillow" not in missing_required:
        try:
            from PIL import features
            if not features.check("webp"):
                missing_required.append("Pillow WebP codec")
                print("MISSING: Pillow has no WebP support")
        except (ImportError, OSError) as exc:
            missing_required.append("Pillow WebP support")
            print(f"MISSING: cannot check Pillow WebP support ({exc})")
    if missing_required:
        print("Install missing requirements using the active Python environment.", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print("Usage: python skill.py {search|more|finalize|check} [arguments...]")
        return 0
    if sys.argv[1] in {"-V", "--version"}:
        print("0.3.0")
        return 0
    command = sys.argv[1]
    if command == "check":
        return check()
    script = COMMANDS.get(command)
    if script is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        return 2
    completed = subprocess.run([sys.executable, str(script), *sys.argv[2:]], check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
