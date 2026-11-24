from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

_warned_sinks: set[int] = set()
_sink_refs: list[Callable[[str], None]] = []


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items: list[Any] = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = []
    cleaned = (v.strip() for v in items if isinstance(v, str))
    return [v for v in cleaned if v]


def read_roles(claims: Mapping | None, role_claim: str) -> list[str]:
    if not isinstance(claims, Mapping):
        return []
    return _clean_list(claims.get(role_claim))


def read_default_role(claims: Mapping | None, default_role_claim: str) -> str | None:
    if not isinstance(claims, Mapping):
        return None
    value = claims.get(default_role_claim)
    role = value.strip() if isinstance(value, str) else ""
    return role or None


def has_any_role(roles: Sequence[str], required: str | Sequence[str]) -> bool:
    wanted = _clean_list(required)
    if not wanted:
        raise ValueError("required roles must be non-empty")
    return any(r in roles for r in wanted)


def warn_if_no_role_claim(
    claims: Mapping | None, role_claim: str, log: Callable[[str], None]
) -> bool:
    if read_roles(claims, role_claim):
        return False
    key = id(log)
    if key not in _warned_sinks:
        # Holding a reference keeps id() from being reused by a different sink.
        _warned_sinks.add(key)
        _sink_refs.append(log)
        log(
            f's4-auth: the signed-in user\'s token carries no "{role_claim}" claim — this app client is not in '
            "the pool's claims-emission set (or the pool has no role Lambda). The data layer will apply its "
            "own default role. Do not remove an admin secret until the emission set includes this client."
        )
    return True
