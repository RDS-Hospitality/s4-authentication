from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

from markupsafe import escape

import requests
from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client import OAuthError
from cachelib import SimpleCache
from flask import Blueprint, Flask, Response, abort, after_this_request, current_app, redirect, request, session, url_for
from flask.sessions import SessionInterface, SessionMixin
from flask_session import Session
from joserfc.errors import JoseError

from s4_auth_flask.config import AuthConfig
from s4_auth_flask.guards import adapter_view, deny, guard, request_is_same_origin, signed_in
from s4_auth_flask.redirects import safe_return_path
from s4_auth_flask.tokens import TokenInvalid, verify_id_token

TOKENS = "s4.tokens"
CLAIMS = "s4.claims"
RETURN_TO = "s4.return_to"
LAST_ACTIVITY = "s4.last_activity"
STATE_KEYS = (TOKENS, CLAIMS, RETURN_TO, LAST_ACTIVITY)

# Every way a callback can fail to produce a verified sign-in; all land on a fresh login.
_CALLBACK_FAILURES = (OAuthError, JoseError, TokenInvalid)

_log = logging.getLogger("s4_auth_flask")

# Mirrors what Flask-Session's DynamoDB interface reads and writes (dynamodb.py: KeySchema "id",
# TTL "expiration"); the adapter never creates the table, so setup docs quote this.
# The table must have TTL enabled on `expiration`; the adapter never enables it (housekeeping only,
# lifetime is enforced by the idle timeout and Cognito's refresh-token expiry).
DYNAMODB_TABLE_SHAPE = {
    "partition_key": "id",
    "key_type": "S",
    "ttl_attribute": "expiration",
    "ttl_enabled": True,
}

_ACTIVITY_WRITE_INTERVAL = 60
_REFRESH_SKEW = 60
_HTTP_TIMEOUT = 10


def _now() -> float:
    return time.time()


def _expire_cookie(response: Any) -> Any:
    app = current_app
    interface = app.session_interface
    response.delete_cookie(
        interface.get_cookie_name(app),
        domain=interface.get_cookie_domain(app),
        path=interface.get_cookie_path(app),
        secure=interface.get_cookie_secure(app),
        httponly=interface.get_cookie_httponly(app),
        samesite=interface.get_cookie_samesite(app),
    )
    return response


class _NeverCreateTable:
    """Resource proxy whose create_table reports the table as already existing.

    Flask-Session's DynamoDB interface calls create_table unconditionally at startup and
    ignores SESSION_DYNAMODB_TABLE_EXISTS; the adapter must never create AWS resources.
    """

    def __init__(self, resource: Any) -> None:
        self._resource = resource

    def create_table(self, **_: Any) -> None:
        raise self._resource.meta.client.exceptions.ResourceInUseException(
            {"Error": {"Code": "ResourceInUseException", "Message": "table is managed outside the adapter"}},
            "CreateTable",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resource, name)


class _UnusableSession(dict, SessionMixin):
    """Stand-in when the session store failed; the guard denies on it and it is never saved."""

    s4_unusable = True


class _FailClosedSessions(SessionInterface):
    """Wraps the real interface so a store failure becomes an unusable session, not a 500.

    Flask opens the session before before_request runs, so a guard cannot catch the error.
    """

    def __init__(self, inner: SessionInterface) -> None:
        self._inner = inner

    def open_session(self, app: Flask, req: Any) -> Any:
        try:
            return self._inner.open_session(app, req)
        except Exception:
            _log.exception("s4-auth: session store failed on open; denying the request")
            return _UnusableSession()

    def save_session(self, app: Flask, sess: Any, response: Any) -> None:
        if getattr(sess, "s4_unusable", False):
            _log.warning("s4-auth: not saving a session whose store failed on open")
            return None
        # A failed write must surface as a 500: swallowing it would send a user who just
        # signed in back through the login redirect with no cookie and no visible error.
        return self._inner.save_session(app, sess, response)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class S4Auth:
    def __init__(
        self,
        app: Flask | None = None,
        config: AuthConfig | None = None,
        *,
        session_resource: Any = None,
    ) -> None:
        self.session_resource = session_resource
        self.config: AuthConfig | None = None
        self.oauth: OAuth | None = None
        if app is not None:
            if config is None:
                raise ValueError("config is required when app is given")
            self.init_app(app, config)

    def init_app(self, app: Flask, config: AuthConfig) -> None:
        self.config = config
        self._configure_sessions(app, config)
        self._register_client(app, config)
        app.register_blueprint(self._blueprint(config), url_prefix="/auth")
        # Inserted first: an app hook registered earlier must not run before the guard.
        app.before_request_funcs.setdefault(None, []).insert(0, guard)
        app.extensions["s4_auth"] = self

    def _configure_sessions(self, app: Flask, config: AuthConfig) -> None:
        """Server-side session store and cookie policy. The one place Flask-Session is set up."""
        path = urlsplit(config.base_url).path.rstrip("/") or "/"
        app.config.update(
            SESSION_PERMANENT=True,
            PERMANENT_SESSION_LIFETIME=config.refresh_ttl,
            SESSION_REFRESH_EACH_REQUEST=False,
            SESSION_COOKIE_NAME=config.cookie_name,
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            SESSION_COOKIE_PATH=path,
        )
        if config.session_backend == "dynamodb":
            if self.session_resource is None:
                raise ValueError(
                    'session_backend="dynamodb" requires S4Auth(..., session_resource=<boto3 dynamodb resource>)'
                )
            app.config.update(
                SESSION_TYPE="dynamodb",
                SESSION_DYNAMODB=_NeverCreateTable(self.session_resource),
                SESSION_DYNAMODB_TABLE=config.session_table,
                SESSION_DYNAMODB_TABLE_EXISTS=True,
            )
        else:
            app.config.update(SESSION_TYPE="cachelib", SESSION_CACHELIB=SimpleCache())
        Session(app)
        app.session_interface = _FailClosedSessions(app.session_interface)

    def end_session(self) -> bool:
        """Revoke the refresh token (best effort), delete the server record and expire the cookie.

        Returns False when the server record could not be deleted (store down); the cookie is
        still expired and the session is marked unusable so nothing is saved back to it.
        """
        interface = current_app.session_interface
        after_this_request(_expire_cookie)
        if getattr(session, "s4_unusable", False):
            _log.error("s4-auth: session store unavailable; could not end the server session")
            return False
        refresh_token = (session.get(TOKENS) or {}).get("refresh_token")
        if refresh_token:
            try:
                requests.post(
                    self.config.revoke_url,
                    data={"token": refresh_token, "client_id": self.config.client_id},
                    timeout=_HTTP_TIMEOUT,
                )
            except Exception:
                _log.warning("s4-auth: token revocation failed; ending the session anyway")
        try:
            interface._delete_session(interface._get_store_id(session.sid))
        except Exception:
            _log.exception("s4-auth: could not delete the server session record")
            session.clear()
            session.s4_unusable = True
            return False
        # A later deny() may write to this session again, so move to a fresh id so the old
        # cookie can never match a record.
        session.clear()
        session.sid = interface._generate_sid(interface.sid_length)
        return True

    def enforce_lifetime(self) -> Any:
        """Idle timeout, silent refresh and throttled activity stamp for a signed-in request.

        Returns a deny response when the session had to end, otherwise None.
        """
        now = _now()
        last = session.get(LAST_ACTIVITY)
        if not isinstance(last, (int, float)) or now - last > self.config.idle_timeout.total_seconds():
            self.end_session()
            return deny()
        expires_at = (session.get(TOKENS) or {}).get("expires_at")
        if not isinstance(expires_at, (int, float)) or now >= expires_at - _REFRESH_SKEW:
            if not self._refresh(now):
                self.end_session()
                return deny()
        if now - last >= _ACTIVITY_WRITE_INTERVAL:
            session[LAST_ACTIVITY] = now
        return None

    def _refresh(self, now: float) -> bool:
        tokens = session.get(TOKENS) or {}
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return False
        client = self.oauth.s4
        try:
            endpoint = client.load_server_metadata()["token_endpoint"]
            resp = requests.post(
                endpoint,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.config.client_id,
                    "refresh_token": refresh_token,
                },
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                return False
            body = resp.json()
            claims = verify_id_token(
                body["id_token"], config=self.config, jwks=client.fetch_jwk_set()
            )
        except (*_CALLBACK_FAILURES, requests.RequestException, KeyError, ValueError):
            _log.warning("s4-auth: token refresh failed; ending the session")
            return False
        session[TOKENS] = {
            "id_token": body["id_token"],
            "access_token": body.get("access_token"),
            # Cognito's refresh reply carries no new refresh token; keep the one we hold.
            "refresh_token": body.get("refresh_token") or refresh_token,
            "expires_at": self._expires_at(now, body.get("expires_in"), claims),
        }
        session[CLAIMS] = claims
        return True

    def _expires_at(self, now: float, expires_in: Any, claims: Any) -> float:
        """Earliest of the IdP's stated lifetime, the configured access_ttl and the ID token's exp."""
        limits = [now + self.config.access_ttl.total_seconds()]
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            limits.append(now + expires_in)
        exp = claims.get("exp")
        if isinstance(exp, (int, float)):
            limits.append(exp)
        return min(limits)

    def _register_client(self, app: Flask, config: AuthConfig) -> None:
        self.oauth = OAuth(app)
        self.oauth.register(
            "s4",
            client_id=config.client_id,
            client_secret=None,
            server_metadata_url=config.metadata_url,
            client_kwargs={
                "scope": " ".join(config.scopes),
                "code_challenge_method": "S256",
                "default_timeout": _HTTP_TIMEOUT,
            },
        )

    def _blueprint(self, config: AuthConfig) -> Blueprint:
        bp = Blueprint("s4_auth", __name__)
        client = self.oauth.s4

        def landing(return_to: str | None) -> Any:
            target = safe_return_path(return_to, request.script_root)
            return redirect(target or _mounted(config.post_login_route), 303)

        @bp.get("/login")
        @adapter_view
        def login() -> Any:
            if getattr(session, "s4_unusable", False):
                return _unavailable()
            if signed_in():
                return landing(session.get(RETURN_TO))
            extra = {}
            if config.identity_provider:
                extra["identity_provider"] = config.identity_provider
            return client.authorize_redirect(config.callback_url, **extra)

        @bp.get("/callback")
        @adapter_view
        def callback() -> Any:
            if getattr(session, "s4_unusable", False):
                return _unavailable()
            if request.args.get("error"):
                # The IdP refused the user; sending them back to the IdP would loop.
                reason = request.args.get("error_description") or request.args["error"]
                return _page(401, "Sign-in was refused", escape(reason), _login_url())
            return_to = session.get(RETURN_TO)
            try:
                token = client.authorize_access_token()
                claims = verify_id_token(
                    token["id_token"], config=config, jwks=client.fetch_jwk_set()
                )
            except requests.RequestException:
                _log.warning("s4-auth: identity provider unreachable at callback")
                return _unavailable()
            except (*_CALLBACK_FAILURES, KeyError):
                for key in STATE_KEYS:
                    session.pop(key, None)
                return redirect(_login_url(), 302)
            session.pop(RETURN_TO, None)
            session[TOKENS] = {
                "id_token": token["id_token"],
                "access_token": token.get("access_token"),
                "refresh_token": token.get("refresh_token"),
                "expires_at": self._expires_at(_now(), token.get("expires_in"), claims),
            }
            session[CLAIMS] = claims
            session[LAST_ACTIVITY] = _now()
            current_app.session_interface.regenerate(session)
            return landing(return_to)

        @bp.post("/logout")
        @adapter_view
        def logout() -> Any:
            # Exempt from the guard so an expired session can still log out; the origin check
            # is the CSRF defence, and a request carrying neither header is refused.
            if not request_is_same_origin(config.base_url):
                abort(403)
            if not self.end_session():
                return Response("Sign-out could not be completed; try again shortly.", 503)
            return redirect(config.logout_url, 303)

        @bp.get("/signed-out")
        @adapter_view
        def signed_out() -> Any:
            # Cognito's logout lands here. It must never redirect: a redirect to a guarded
            # page would start a new sign-in the user did not ask for.
            return _page(200, "You are signed out.", "", _login_url(), "Sign in")

        return bp


def _page(status: int, title: str, detail: Any, link: str, link_text: str = "Try again") -> Response:
    body = (
        f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{title}</title></head>"
        f"<body><h1>{title}</h1><p>{detail}</p><p><a href=\"{link}\">{link_text}</a></p></body></html>"
    )
    return Response(body, status, mimetype="text/html")


def _unavailable() -> Response:
    return _page(
        503, "Sign-in is temporarily unavailable", "Please try again in a moment.", _login_url()
    )


def _mounted(path: str) -> str:
    return request.script_root + path


def _login_url() -> str:
    return url_for("s4_auth.login")
