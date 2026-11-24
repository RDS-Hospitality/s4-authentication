from __future__ import annotations

import re
from typing import Sequence
from urllib.parse import urlsplit

_ABSOLUTE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_DEFAULT_PORTS = {"http": 80, "https": 443}
_DOT = re.compile(r"^(\.|%2e)$", re.IGNORECASE)
_DOTDOT = re.compile(r"^(\.|%2e){2}$", re.IGNORECASE)


def _strip_trailing_slash(path: str) -> str:
    return path[:-1] if len(path) > 1 and path.endswith("/") else path


def _path_of(url_or_path: str) -> str:
    cut = re.search(r"[?#]", url_or_path)
    return url_or_path if cut is None else url_or_path[: cut.start()]


def _at_segment_boundary(request_path: str, entry_path: str) -> bool:
    if entry_path in ("", "/"):
        return True
    return request_path == entry_path or request_path.startswith(entry_path + "/")


def _normalize_path(path: str) -> str:
    # WHATWG URL resolves dot segments before a server sees the path, so do the same here.
    out: list[str] = []
    for seg in path.split("/")[1:] or [""]:
        if _DOTDOT.match(seg):
            if out:
                out.pop()
        elif not _DOT.match(seg):
            out.append(seg)
    return "/" + "/".join(out)


def _origin_key(parts) -> tuple[str, str, int | None] | None:
    try:
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if not host:
        return None
    scheme = parts.scheme.lower()
    if port == _DEFAULT_PORTS.get(scheme):
        port = None
    return scheme, host.lower(), port


def _matches_absolute(url: str, entry: str) -> bool:
    try:
        e = urlsplit(entry)
        u = urlsplit(url)
    except ValueError:
        return False
    ek, uk = _origin_key(e), _origin_key(u)
    if ek is None or uk is None or e.query or e.fragment:
        return False
    if ek != uk:
        return False
    return _at_segment_boundary(
        _strip_trailing_slash(_normalize_path(u.path or "/")),
        _strip_trailing_slash(_normalize_path(e.path or "/")),
    )


def _matches_path_prefix(url: str, entry: str, current_origin: str | None) -> bool:
    normalized_entry = _strip_trailing_slash(entry)
    if normalized_entry == "/" or re.search(r"[?#]", entry):
        return False
    if url.startswith("//"):
        return False
    path = url
    if _ABSOLUTE.match(url):
        if not current_origin or not url.lower().startswith(current_origin.lower() + "/"):
            return False
        path = url[len(current_origin):]
    return _at_segment_boundary(_strip_trailing_slash(_path_of(path)), normalized_entry)


def matches_allowlist(url: str, entries: Sequence[str], current_origin: str) -> bool:
    for raw in entries:
        entry = raw.strip()
        if not entry:
            continue
        if _ABSOLUTE.match(entry):
            if _matches_absolute(url, entry):
                return True
        elif entry.startswith("/"):
            if _matches_path_prefix(url, entry, current_origin):
                return True
    return False
