#!/usr/bin/env python3
"""Portable skill launcher. Automatically prepares isolated dependencies on first use."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
VERSION = "0.5.3"
COMMANDS = {
    "search": SCRIPTS_DIR / "image_search.py",
    "more": SCRIPTS_DIR / "download_more.py",
    "finalize": SCRIPTS_DIR / "finalize_image.py",
    "review": SCRIPTS_DIR / "review_candidates.py",
    "evaluate": SCRIPTS_DIR / "evaluate_runs.py",
}
READY_PROBE = "import requests; from PIL import features; assert features.check('webp')"


def current_python_ready() -> bool:
    if not (importlib.util.find_spec("requests") and importlib.util.find_spec("PIL")):
        return False
    try:
        from PIL import features
        return bool(features.check("webp"))
    except (ImportError, OSError):
        return False


def managed_python(folder: Path) -> Path:
    if os.name == "nt":
        return folder / "Scripts" / "python.exe"
    return folder / "bin" / "python"


def python_works(executable: Path) -> bool:
    if not executable.is_file():
        return False
    try:
        result = subprocess.run(
            [str(executable), "-c", READY_PROBE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def project_root(command_args: list[str]) -> Path:
    for index, value in enumerate(command_args):
        if value == "--root" and index + 1 < len(command_args):
            return Path(command_args[index + 1]).expanduser().resolve()
        if value.startswith("--root="):
            return Path(value.split("=", 1)[1]).expanduser().resolve()
    return Path.cwd().resolve()


def environment_locations(command_args: list[str]) -> list[Path]:
    custom = os.environ.get("WEBSITE_IMAGE_FINDER_CACHE_DIR")
    if custom:
        return [Path(custom).expanduser() / ("py" + str(sys.version_info.major) + str(sys.version_info.minor))]
    cache = (Path(os.environ.get("LOCALAPPDATA", "")) if os.name == "nt" and os.environ.get("LOCALAPPDATA")
             else Path.home() / ".cache")
    version = "py" + str(sys.version_info.major) + str(sys.version_info.minor)
    # The project-local fallback works for coding agents whose sandbox blocks home writes.
    return [cache / "website-image-finder" / version,
            project_root(command_args) / ".image-search" / ".venv"]


def install_isolated(folder: Path) -> Path:
    folder.parent.mkdir(parents=True, exist_ok=True)
    python = managed_python(folder)
    if not python.is_file():
        subprocess.run(
            [sys.executable, "-m", "venv", str(folder)],
            check=True, timeout=120,
        )
    if not python_works(python):
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-input",
             "--disable-pip-version-check", "-r", str(SKILL_DIR / "requirements.txt")],
            check=True, timeout=240,
        )
    if not python_works(python):
        raise RuntimeError("The installed Pillow build has no WebP support")
    return python


def prepared_python(args: list[str], *, allow_install: bool) -> Path | None:
    locations = environment_locations(args)
    for folder in locations:
        executable = managed_python(folder)
        if python_works(executable):
            return executable
    if current_python_ready() and not allow_install:
        return Path(sys.executable)
    if current_python_ready() and args and args[0] != "setup":
        return Path(sys.executable)
    if not allow_install:
        return None
    errors: list[str] = []
    for folder in locations:
        try:
            print("Preparing isolated Python dependencies in " + str(folder), file=sys.stderr)
            return install_isolated(folder)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            errors.append(str(folder) + ": " + type(exc).__name__ + ": " + str(exc))
    print("Automatic dependency setup failed. Try: python -m pip install -r " +
          str(SKILL_DIR / "requirements.txt"), file=sys.stderr)
    for error in errors:
        print("  " + error, file=sys.stderr)
    return None


def check(args: list[str] | None = None) -> int:
    args = args or []
    for name, label in (("requests", "requests"), ("PIL", "Pillow"), ("ddgs", "DDGS (optional)")):
        print(("OK" if importlib.util.find_spec(name) else "INFO") + ": " + label)
    ready = current_python_ready()
    if ready:
        print("OK: current Python can download/process images")
    else:
        for folder in environment_locations(["check", *args]):
            if python_works(managed_python(folder)):
                ready = True
                print("OK: isolated Python is ready at " + str(managed_python(folder)))
                break
    if not ready:
        print("INFO: dependencies missing; run setup or let the next search install them automatically")
    has_key = bool((os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERPAPI_KEY") or "").strip())
    print("INFO: SerpApi key " + ("is configured (paid search still requires --provider serpapi)"
                                  if has_key else "is not configured; no key is needed for free search"))
    return 0 if ready else 2


def main() -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return 2
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print("Usage: python skill.py {search|more|finalize|review|evaluate|check|setup} [arguments...]")
        print("Free search needs no API key. First run installs dependencies into an isolated environment.")
        return 0
    if sys.argv[1] in {"-V", "--version"}:
        print(VERSION)
        return 0
    command = sys.argv[1]
    if command == "check":
        return check(sys.argv[2:])
    if command != "setup" and command not in COMMANDS:
        print("Unknown command: " + command, file=sys.stderr)
        return 2
    arguments = sys.argv[2:]
    if any(value in {"-h", "--help"} for value in arguments):
        if command == "setup":
            print("Usage: python skill.py setup [--root PROJECT_DIR]")
            return 0
        return subprocess.run([sys.executable, str(COMMANDS[command]), *arguments], check=False).returncode

    auto_setup = os.environ.get("WEBSITE_IMAGE_FINDER_AUTO_SETUP", "1") != "0"
    python = prepared_python([command, *arguments], allow_install=(command == "setup" or auto_setup))
    if python is None:
        print("Missing dependencies and automatic installation is disabled or unavailable. "
              "Run: python scripts/skill.py setup", file=sys.stderr)
        return 2
    if command == "setup":
        print("Ready: " + str(python))
        return 0
    try:
        return subprocess.run([str(python), str(COMMANDS[command]), *arguments], check=False).returncode
    except OSError as exc:
        print("Cannot launch skill command: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
