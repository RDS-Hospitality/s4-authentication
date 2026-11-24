"""Static self-conformance checks over the shipped package source.

Each check is a function of a package directory so it can be pointed at a planted copy and
shown to catch a violation.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

import s4_auth_flask

PACKAGE = Path(s4_auth_flask.__file__).parent


def _sources(pkg: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(pkg.glob("*.py"))}


def find_implicit_flow(pkg: Path) -> list[str]:
    return [n for n, t in _sources(pkg).items() if re.search(r"response_type\s*=\s*['\"]?token", t)]


def find_unverified_decode(pkg: Path) -> list[str]:
    hits = []
    for name, text in _sources(pkg).items():
        if "verify=False" in text or re.search(r"""["']verify_signature["']\s*:\s*False""", text):
            hits.append(name)
        elif "jwt.decode(" in text and name != "tokens.py":
            hits.append(name)
    return hits


def find_env_reads(pkg: Path) -> list[str]:
    sources = _sources(pkg)
    return [
        name
        for name in ("guards.py", "extension.py")
        if re.search(r"os\.environ|getenv", sources[name])
    ]


def find_client_secret(pkg: Path) -> list[str]:
    return [
        n
        for n, t in _sources(pkg).items()
        if re.search(r"client_secret\s*=\s*(?!None\b)\S", t)
    ]


CHECKS = [
    ("response_type=token", "extension.py", find_implicit_flow),
    ("verify=False", "extension.py", find_unverified_decode),
    ("options={'verify_signature': False}", "tokens.py", find_unverified_decode),
    ("os.environ.get('X')", "guards.py", find_env_reads),
    ("getenv('X')", "extension.py", find_env_reads),
    ("client_secret='abc'", "extension.py", find_client_secret),
]


def test_no_implicit_flow():
    assert find_implicit_flow(PACKAGE) == []


def test_no_unverified_decode():
    assert find_unverified_decode(PACKAGE) == []


def test_no_guard_kill_switch():
    assert find_env_reads(PACKAGE) == []


def test_no_secret_in_package():
    assert find_client_secret(PACKAGE) == []


def test_decode_outside_tokens_is_caught(tmp_path):
    pkg = _plant(tmp_path, "guards.py", "x = jwt.decode(t, k)")
    assert find_unverified_decode(pkg) == ["guards.py"]


@pytest.mark.parametrize("planted,target,check", CHECKS)
def test_check_catches_planted_violation(tmp_path, planted, target, check):
    pkg = _plant(tmp_path, target, planted)
    assert target in check(pkg)


def _plant(tmp_path: Path, target: str, line: str) -> Path:
    pkg = tmp_path / "s4_auth_flask"
    shutil.copytree(PACKAGE, pkg, ignore=shutil.ignore_patterns("__pycache__"))
    with (pkg / target).open("a") as f:
        f.write(f"\n{line}\n")
    return pkg
