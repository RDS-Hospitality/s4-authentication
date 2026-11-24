from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from flask import Response, abort, current_app, redirect, request, session, url_for

from s4_auth_flask.roles import has_any_role, read_roles, warn_if_no_role_claim
from s4_auth_flask.url_allowlist import matches_allowlist

_PUBLIC_ATTR = "_s4_public"
_ADAPTER_ATTR = "_s4_adapter_view"
_log = logging.getLogger("s4_auth_flask")


def _warn(message: str) -> None:
    _log.warning(message)


def public(view: Callable) -> Callable:
    """Exempt a view from the default-deny guard."""
    setattr(view, _PUBLIC_ATTR, True)
    return view


def _auth():
    return current_app.extensions["s4_auth"]


def adapter_view(view: Callable) -> Callable:
    """Mark a view the adapter itself registered; only these are exempt by identity."""
    setattr(view, _ADAPTER_ATTR, True)
    return view


def _claims() -> Mapping | None:
    """Verified claims of the signed-in user, or None. The one definition of "signed in"."""
    if getattr(session, "s4_unusable", False):
        return None
    from s4_auth_flask.extension import CLAIMS

    claims = session.get(CLAIMS)
    if not isinstance(claims, Mapping):
        return None
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        return None
    return claims


def signed_in() -> bool:
    return _claims() is not None


def _tokens() -> dict:
    from s4_auth_flask.extension import TOKENS

    return session.get(TOKENS) or {}


def _is_exempt() -> bool:
    endpoint = request.endpoint
    if endpoint is None:
        return True  # no view will run: 404/405 handling
    if endpoint == "static":
        return True
    view = current_app.view_functions.get(endpoint)
    # Identity, not endpoint name: Werkzeug derives request.blueprint from the name prefix,
    # so an app view registered as "s4_auth.x" must not inherit the adapter's exemption.
    return bool(getattr(view, _PUBLIC_ATTR, False) or getattr(view, _ADAPTER_ATTR, False))


def deny() -> Response:
    """Refuse an unauthenticated request: login redirect for page loads, 401 for the rest.

    Only a GET that accepts HTML is redirected, and only then is the return path remembered;
    a replayed POST or a JSON call must not be turned into a later GET navigation.
    """
    from s4_auth_flask.extension import RETURN_TO

    wants_html = request.method == "GET" and "text/html" in request.headers.get("Accept", "")
    if not wants_html:
        return Response("Unauthorized", 401)
    if not getattr(session, "s4_unusable", False):
        target = request.script_root + request.path
        if request.query_string:
            target += "?" + request.query_string.decode("latin-1")
        session[RETURN_TO] = target
    return redirect(url_for("s4_auth.login"), 302)


def guard() -> Response | None:
    """before_request hook: every request is denied unless exempt or signed in."""
    if _is_exempt():
        return None
    claims = _claims()
    if claims is None:
        return deny()
    warn_if_no_role_claim(claims, _auth().config.role_claim, _warn)
    return _auth().enforce_lifetime()


def current_roles() -> list[str]:
    return read_roles(_claims(), _auth().config.role_claim)


def has_role(required: str | Sequence[str]) -> bool:
    return has_any_role(current_roles(), required)


def require_role(required: str | Sequence[str]) -> Callable:
    has_any_role([], required)  # raises ValueError on an empty requirement, at decoration time

    def decorator(view: Callable) -> Callable:
        @functools.wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if _claims() is None:
                return deny()
            if not has_role(required):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def current_user() -> dict | None:
    claims = _claims()
    if claims is None:
        return None
    return {**claims, "roles": current_roles()}


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def auth_headers(url: str) -> dict[str, str]:
    """Bearer header for a data-layer URL, only if the URL is on the configured allowlist."""
    config = _auth().config
    token = _tokens().get("id_token")
    if not token or not matches_allowlist(url, config.graphql_urls, _origin_of(config.base_url)):
        return {}
    return {"Authorization": f"Bearer {token}"}
