from __future__ import annotations

from urllib.parse import unquote, urlsplit


def safe_return_path(candidate: str | None, script_root: str = "") -> str | None:
    """Return `candidate` only if it is a same-origin relative path under `script_root`."""
    if not candidate or not candidate.startswith("/"):
        return None
    if candidate.startswith("//") or "\\" in candidate:
        return None
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in candidate):
        return None
    # Percent-decoding must not reveal a protocol-relative or backslash form.
    decoded = unquote(candidate)
    if decoded.startswith("//") or "\\" in decoded:
        return None
    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc:
        return None
    root = script_root.rstrip("/")
    if root and not (parts.path == root or parts.path.startswith(root + "/")):
        return None
    return candidate
