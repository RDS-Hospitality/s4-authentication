import pytest

from s4_auth_flask.roles import has_any_role, read_default_role, read_roles, warn_if_no_role_claim

RC = "hasura_allowed_roles"
DRC = "hasura_default_role"


class Sink:
    def __init__(self):
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)


def test_warn_logs_once_and_returns_true_when_no_role_fields():
    log = Sink()
    assert warn_if_no_role_claim({}, RC, log) is True
    assert len(log.messages) == 1


def test_warn_does_not_log_again_for_same_sink():
    log = Sink()
    warn_if_no_role_claim({}, RC, log)
    assert warn_if_no_role_claim({}, RC, log) is True
    assert len(log.messages) == 1


def test_warn_once_per_sink_not_global():
    a, b = Sink(), Sink()
    warn_if_no_role_claim({}, RC, a)
    warn_if_no_role_claim({}, RC, b)
    assert len(a.messages) == 1 and len(b.messages) == 1


def test_warn_when_default_role_present_but_allowed_roles_absent():
    log = Sink()
    warn_if_no_role_claim({DRC: "x"}, RC, log)
    assert log.messages


def test_no_warn_when_allowed_roles_present():
    log = Sink()
    assert warn_if_no_role_claim({RC: ["a"]}, RC, log) is False
    assert log.messages == []


def test_warn_when_allowed_roles_empty():
    log = Sink()
    warn_if_no_role_claim({RC: []}, RC, log)
    assert len(log.messages) == 1


def test_warn_message_names_emission_set_and_claim():
    log = Sink()
    warn_if_no_role_claim({}, "my_claim", log)
    assert "emission set" in log.messages[0].lower()
    assert '"my_claim"' in log.messages[0]


def test_warn_treats_none_claims_as_claimless():
    assert warn_if_no_role_claim(None, RC, Sink()) is True


def test_read_roles_wraps_single_string():
    assert read_roles({RC: "site"}, RC) == ["site"]


def test_read_roles_trims_and_drops_empty():
    assert read_roles({RC: [" a ", ""]}, RC) == ["a"]


def test_read_roles_does_not_dedupe():
    assert read_roles({RC: ["a", "a", " b "]}, RC) == ["a", "a", "b"]


def test_read_roles_drops_whitespace_only():
    assert read_roles({RC: ["a", "   "]}, RC) == ["a"]


def test_read_roles_drops_non_strings():
    assert read_roles({RC: ["a", 123, None]}, RC) == ["a"]


def test_read_roles_empty_cases():
    assert read_roles({}, RC) == []
    assert read_roles(None, RC) == []
    assert read_roles("not-an-object", RC) == []


def test_read_roles_uses_given_claim_name():
    assert read_roles({"other": ["x"], RC: ["y"]}, "other") == ["x"]


def test_read_default_role():
    assert read_default_role({DRC: " site "}, DRC) == "site"
    assert read_default_role({DRC: 7}, DRC) is None
    assert read_default_role({}, DRC) is None
    assert read_default_role(None, DRC) is None


def test_has_any_role_throws_on_empty_list():
    with pytest.raises(ValueError):
        has_any_role(["a"], [])


def test_has_any_role_throws_on_empty_string():
    with pytest.raises(ValueError):
        has_any_role(["a"], "")


def test_has_any_role_throws_on_blank_only():
    with pytest.raises(ValueError):
        has_any_role(["a"], [" ", ""])


def test_has_any_role_case_sensitive_any_match():
    assert has_any_role(["site", "office"], "office") is True
    assert has_any_role(["site"], ["Site"]) is False
    assert has_any_role([], "site") is False
