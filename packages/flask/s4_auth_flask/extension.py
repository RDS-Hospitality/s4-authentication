from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client import OAuthError
from cachelib import SimpleCache
from flask import Blueprint, Flask, abort, current_app, redirect, request, session, url_for
from flask.sessions import SessionInterface, SessionMixin
from flask_session import Session
from joserfc.errors import JoseError

from s4_auth_flask.config import AuthConfig
from s4_auth_flask.guards import adapter_view, deny, guard, signed_in
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

_ACTIVITY_WRITE_INTERVAL = 60
_REFRESH_SKEW = 60
_HTTP_TIMEOUT = 10


def _now() -> float:
    return time.time()


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


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
        app.before_request(guard)
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
            app.config.update(
                SESSION_TYPE="dynamodb",
                SESSION_DYNAMODB=self.session_resource,
                SESSION_DYNAMODB_TABLE_NAME=config.session_table,
                SESSION_DYNAMODB_TABLE_EXISTS=True,
            )
        else:
            app.config.update(SESSION_TYPE="cachelib", SESSION_CACHELIB=SimpleCache())
        Session(app)
        app.session_interface = _FailClosedSessions(app.session_interface)

    def end_session(self) -> None:
        """Revoke the refresh token (best effort), delete the server record and expire the cookie."""
        if getattr(session, "s4_unusable", False):
            return
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
        interface = current_app.session_interface
        # Clearing alone leaves the record until save; a later deny() may write to this session
        # again, so delete now and move to a fresh id so the old cookie can never match a record.
        interface._delete_session(interface._get_store_id(session.sid))
        session.clear()
        session.sid = interface._generate_sid(interface.sid_length)

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
        expires_in = body.get("expires_in") or self.config.access_ttl.total_seconds()
        session[TOKENS] = {
            "id_token": body["id_token"],
            "access_token": body.get("access_token"),
            # Cognito's refresh reply carries no new refresh token; keep the one we hold.
            "refresh_token": body.get("refresh_token") or refresh_token,
            "expires_at": now + expires_in,
        }
        session[CLAIMS] = claims
        return True

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
            if signed_in():
                return landing(session.get(RETURN_TO))
            extra = {}
            if config.identity_provider:
                extra["identity_provider"] = config.identity_provider
            return client.authorize_redirect(config.callback_url, **extra)

        @bp.get("/callback")
        @adapter_view
        def callback() -> Any:
            return_to = session.get(RETURN_TO)
            try:
                token = client.authorize_access_token()
                claims = verify_id_token(
                    token["id_token"], config=config, jwks=client.fetch_jwk_set()
                )
            except (*_CALLBACK_FAILURES, KeyError):
                for key in STATE_KEYS:
                    session.pop(key, None)
                return redirect(_login_url(), 302)
            session.pop(RETURN_TO, None)
            session[TOKENS] = {
                "id_token": token["id_token"],
                "access_token": token.get("access_token"),
                "refresh_token": token.get("refresh_token"),
                "expires_at": token.get("expires_at"),
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
            source = request.headers.get("Origin") or request.headers.get("Referer")
            if not source or _origin(source) != _origin(config.base_url):
                abort(403)
            self.end_session()
            return redirect(config.logout_url, 303)

        return bp


def _mounted(path: str) -> str:
    return request.script_root + path


def _login_url() -> str:
    return url_for("s4_auth.login")
