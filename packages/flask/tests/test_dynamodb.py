from __future__ import annotations

import time

import boto3
import pytest
import responses as responses_lib
from flask import Flask
from moto import mock_aws

from s4_auth_flask import S4Auth, public
from s4_auth_flask.config import AuthConfig
from s4_auth_flask.extension import DYNAMODB_TABLE_SHAPE
from tests.test_flow import HTTPS
from tests.test_guards import HTML, sign_in

TABLE = "s4-auth-sessions"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    # Flask-Session computes the TTL with naive utcnow().timestamp(), which is only right in UTC.
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    with mock_aws():
        yield boto3.resource("dynamodb")
    monkeypatch.undo()
    time.tzset()


def create_table(resource):
    resource.create_table(
        TableName=TABLE,
        AttributeDefinitions=[
            {"AttributeName": DYNAMODB_TABLE_SHAPE["partition_key"], "AttributeType": DYNAMODB_TABLE_SHAPE["key_type"]}
        ],
        KeySchema=[{"AttributeName": DYNAMODB_TABLE_SHAPE["partition_key"], "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def ddb_config(config) -> AuthConfig:
    from dataclasses import replace

    return replace(config, session_backend="dynamodb", session_table=TABLE)


def build_app(cfg, resource):
    app = Flask(__name__)
    app.config["TESTING"] = True
    S4Auth(app, cfg, session_resource=resource)

    @app.get("/reports")
    def reports():
        return "reports"

    return app


@pytest.fixture
def two_apps(aws, ddb_config, idp_mock):
    create_table(aws)
    return build_app(ddb_config, aws), build_app(ddb_config, aws)


def cookie_value(client):
    return client.get_cookie("s4_session").value


def test_two_instances_share_a_session(two_apps, fake_idp):
    a, b = (app.test_client() for app in two_apps)
    sign_in(a, fake_idp)
    b.set_cookie("s4_session", cookie_value(a), domain="localhost")
    assert b.get("/reports", base_url=HTTPS).status_code == 200


def test_logout_on_one_instance_ends_it_on_the_other(two_apps, fake_idp):
    a, b = (app.test_client() for app in two_apps)
    sign_in(a, fake_idp)
    cookie = cookie_value(a)
    b.set_cookie("s4_session", cookie, domain="localhost")
    assert b.get("/reports", base_url=HTTPS).status_code == 200
    assert a.post("/auth/logout", base_url=HTTPS, headers={"Origin": HTTPS}).status_code == 303
    b.set_cookie("s4_session", cookie, domain="localhost")
    assert b.get("/reports", base_url=HTTPS, headers=HTML).status_code == 302


def test_adapter_never_creates_the_table(aws, ddb_config, idp_mock):
    app = build_app(ddb_config, aws)
    client = app.test_client()
    assert client.get("/reports", base_url=HTTPS, headers=HTML).status_code in (302, 401)
    assert client.get("/reports", base_url=HTTPS).status_code in (302, 401)
    assert aws.meta.client.list_tables()["TableNames"] == []


def test_session_item_holds_no_cookie_visible_token(two_apps, aws, fake_idp, ddb_config):
    a = two_apps[0].test_client()
    sign_in(a, fake_idp)
    cookie = cookie_value(a)
    items = aws.Table(TABLE).scan()["Items"]
    assert len(items) == 1
    item = items[0]
    interface = two_apps[0].session_interface
    stored = interface.serializer.decode(bytes(item["val"].value))
    tokens = [v for v in stored["s4.tokens"].values() if isinstance(v, str)]
    assert tokens
    for token in tokens:
        assert cookie not in token
    ttl = float(item[DYNAMODB_TABLE_SHAPE["ttl_attribute"]])
    assert time.time() < ttl <= time.time() + ddb_config.refresh_ttl.total_seconds() + 5
