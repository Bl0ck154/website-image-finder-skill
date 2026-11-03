"""Shared safety and utility helpers."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

VERSION = "0.3.0"
SECRET_NAMES = ("SERPAPI_API_KEY", "SERPAPI_KEY")


class SkillError(RuntimeError):
    pass


def redact(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    result = str(text)
    for secret in secrets:
        if secret:
            result = result.replace(secret, "<redacted>")
    result = re.sub(r"(?i)(api_key=)[^&\s]+", r"\1<redacted>", result)
    result = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1<redacted>", result)
    return result


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def ensure_within_root(path: Path, root: Path, *, label: str = "path") -> Path:
    root_resolved = root.resolve()
    path_resolved = path.resolve(strict=False)
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SkillError(f"{label} must stay inside project root: {root_resolved}") from exc
    return path_resolved


def resolve_under_root(value: str | Path, root: Path, *, label: str = "path") -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return ensure_within_root(path, root, label=label)


def normalize_domain(value: str) -> str:
    raw = value.strip().lower().rstrip(".")
    if not raw:
        raise SkillError("domain cannot be empty")
    if "://" in raw:
        parsed = urlsplit(raw)
        raw = (parsed.hostname or "").lower().rstrip(".")
    raw = raw.lstrip(".")
    if not raw or "/" in raw or "@" in raw or ":" in raw:
        raise SkillError(f"invalid domain: {value}")
    try:
        ascii_domain = raw.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise SkillError(f"invalid domain: {value}") from exc
    labels = ascii_domain.split(".")
    if any(not label or len(label) > 63 or not re.fullmatch(r"[a-z0-9-]+", label) or label.startswith("-") or label.endswith("-") for label in labels):
        raise SkillError(f"invalid domain: {value}")
    return ascii_domain


def domain_of(url: str) -> str:
    host = urlsplit(url).hostname or ""
    try:
        return host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return ""


def host_matches(url: str, domains: list[str]) -> bool:
    host = domain_of(url)
    return bool(host) and any(host == domain or host.endswith("." + domain) for domain in domains)


def validate_remote_url_syntax(url: str, *, allow_nonstandard_ports: bool = False) -> str:
    raw = url.strip()
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in raw) or "\\" in raw:
        raise SkillError("URL contains whitespace, control characters, or backslashes")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SkillError("URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise SkillError("URL user information is not allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SkillError("invalid URL port") from exc
    if not allow_nonstandard_ports and port not in {None, 80, 443}:
        raise SkillError("non-standard URL ports are blocked")

    host = parsed.hostname.rstrip(".")
    if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith(".local"):
        raise SkillError("local hostnames are blocked")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise SkillError("invalid hostname") from exc

    if "%" in ascii_host:
        raise SkillError("scoped IP hostnames are blocked")
    try:
        literal_ip = ipaddress.ip_address(ascii_host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        raise SkillError("local, private, reserved, or link-local destinations are blocked")
    if literal_ip is None:
        if len(ascii_host) > 253:
            raise SkillError("hostname is too long")
        labels = ascii_host.split(".")
        if any(
            not label or len(label) > 63 or not re.fullmatch(r"[a-z0-9-]+", label, re.IGNORECASE)
            or label.startswith("-") or label.endswith("-")
            for label in labels
        ):
            raise SkillError("invalid hostname")
        numeric_pattern = re.compile(r"(?:0x[0-9a-f]+|0[0-7]+|[0-9]+)", re.IGNORECASE)
        if labels and all(numeric_pattern.fullmatch(part) for part in labels):
            raise SkillError("ambiguous numeric hostnames are blocked")

    clean_netloc = ascii_host
    if ":" in ascii_host and not ascii_host.startswith("["):
        clean_netloc = f"[{ascii_host}]"
    if port is not None:
        clean_netloc += f":{port}"
    return urlunsplit((parsed.scheme.lower(), clean_netloc, parsed.path or "/", parsed.query, ""))


def validate_public_url(url: str, *, allow_nonstandard_ports: bool = False) -> str:
    clean_url = validate_remote_url_syntax(url, allow_nonstandard_ports=allow_nonstandard_ports)
    parsed = urlsplit(clean_url)
    ascii_host = parsed.hostname or ""
    port = parsed.port
    try:
        addresses = socket.getaddrinfo(ascii_host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SkillError(f"DNS resolution failed for {ascii_host}") from exc
    if not addresses:
        raise SkillError(f"DNS resolution returned no addresses for {ascii_host}")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise SkillError("local, private, reserved, or link-local destinations are blocked")
    return clean_url


def safe_redirect(current_url: str, location: str) -> str:
    return validate_public_url(urljoin(current_url, location))


def origin_referer(url: str) -> str | None:
    try:
        clean = validate_public_url(url)
    except SkillError:
        return None
    parsed = urlsplit(clean)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def unicode_words(value: str) -> set[str]:
    # Keep common apostrophes and hyphens inside words, including Ukrainian names/terms.
    pattern = r"[^\W_]+(?:['’ʼ-][^\W_]+)*"
    return {
        match.group(0).casefold()
        for match in re.finditer(pattern, value, flags=re.UNICODE)
        if len(match.group(0)) > 2
    }


def canonical_url(url: str) -> str:
    raw = url.strip()
    parsed = urlsplit(raw)
    host = domain_of(raw)
    if not parsed.scheme or not host:
        return raw
    try:
        port = parsed.port
    except ValueError:
        return raw
    netloc = host
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
