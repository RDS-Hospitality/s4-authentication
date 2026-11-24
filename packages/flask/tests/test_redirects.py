import pytest

from s4_auth_flask.redirects import safe_return_path


@pytest.mark.parametrize("value", ["/", "/a/b?x=1"])
def test_accepts_same_origin_paths(value):
    assert safe_return_path(value) == value


def test_script_root_accepts_paths_under_it():
    assert safe_return_path("/app/x", "/app") == "/app/x"
    assert safe_return_path("/app", "/app") == "/app"


def test_script_root_rejects_other_paths():
    assert safe_return_path("/other", "/app") is None
    assert safe_return_path("/application", "/app") is None


@pytest.mark.parametrize(
    "value",
    [
        None, "", "//evil.com", "/\\evil.com", "\\evil.com", "https://evil.com",
        "javascript:alert(1)", "/%2F%2Fevil.com", "\t/evil", "/x\n",
    ],
)
def test_rejects_unsafe(value):
    assert safe_return_path(value) is None
