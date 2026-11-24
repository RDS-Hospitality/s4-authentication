import pytest
import responses as responses_lib

from s4_auth_flask.config import AuthConfig
from tests.fake_idp import FakeIdP


@pytest.fixture
def config() -> AuthConfig:
    return AuthConfig(
        providers=("google",),
        user_pool_id="us-east-1_TESTPOOL1",
        client_id="testclient",
        cognito_domain="test.auth.us-east-1.amazoncognito.com",
        base_url="https://localhost",
        session_backend="memory",
    )


@pytest.fixture
def fake_idp(config) -> FakeIdP:
    return FakeIdP(config)


@pytest.fixture
def idp_mock(fake_idp, config):
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as mock:
        fake_idp.install(mock, config)
        yield mock


@pytest.fixture
def make_app(config, idp_mock):
    from flask import Flask, session

    from s4_auth_flask import S4Auth

    def factory(cfg=None):
        app = Flask(__name__)
        app.config["TESTING"] = True
        S4Auth(app, cfg or config)

        @app.get("/")
        def index():
            return "home"

        @app.get("/seed")
        def seed():
            from flask import request

            session["s4.return_to"] = request.args["to"]
            return "ok"

        @app.get("/whoami")
        def whoami():
            return {"claims": session.get("s4.claims"), "sid_seen": True}

        return app

    return factory
