import pytest

from s4_auth_flask.url_allowlist import matches_allowlist

ORIGIN = "https://app.example.com"

# (id, url, entries, current_origin, expected). Relative request URLs from the TS suite are
# expressed as URLs on ORIGIN, since the Flask side only ever sees absolute URLs.
CASES = [
    ('rejects_different_origin', 'https://evil.example/x', ['https://api.s4hospitality.net'], ORIGIN, False),
    ('path_prefixed_entry', ORIGIN + '/hasura-api/v1/graphql', ['/hasura-api'], ORIGIN, True),
    ('string_prefix_not_boundary', ORIGIN + '/hasura-apiv2/v1/graphql', ['/hasura-api'], ORIGIN, False),
    ('query_string', ORIGIN + '/hasura-api?x=1', ['/hasura-api'], ORIGIN, True),
    ('subdomain_suffix_attack', 'https://api.s4hospitality.net.evil.com/', ['https://api.s4hospitality.net'], ORIGIN, False),
    ('host_case_insensitive', 'https://API.s4hospitality.net/v1/graphql', ['https://api.s4hospitality.net'], ORIGIN, True),
    ('bare_scheme_entry', 'https://api.s4hospitality.net/v1/graphql', ['https://'], ORIGIN, False),
    ('bare_word_entry', 'https://api.s4hospitality.net/v1/graphql', ['api'], ORIGIN, False),
    ('entry_trailing_slash', ORIGIN + '/hasura-api/v1/graphql', ['/hasura-api/'], ORIGIN, True),
    ('path_entry_case_sensitive', ORIGIN + '/Hasura-Api/v1/graphql', ['/hasura-api'], ORIGIN, False),
    ('entry_with_query', ORIGIN + '/hasura-api/v1/graphql', ['/hasura-api?x=1'], ORIGIN, False),
    ('scheme_mismatch', 'http://api.s4hospitality.net/v1/graphql', ['https://api.s4hospitality.net'], ORIGIN, False),
    ('empty_allowlist_absolute', 'https://api.s4hospitality.net/v1/graphql', [], ORIGIN, False),
    ('empty_allowlist_relative', ORIGIN + '/hasura-api/v1/graphql', [], ORIGIN, False),
    ('bare_slash_entry', ORIGIN + '/graphql', ['/'], ORIGIN, False),
    ('bare_slash_entry_protocol_relative', '//evil.example/graphql', ['/'], ORIGIN, False),
    ('protocol_relative_vs_path_entry', '//evil.example/hasura-api/x', ['/hasura-api'], ORIGIN, False),
    ('absolute_same_origin_matches_path_entry', 'https://app.example.com/hasura-api/v1/graphql', ['/hasura-api'], ORIGIN, True),
    ('absolute_same_origin_host_case', 'https://APP.example.com/hasura-api/v1/graphql', ['/hasura-api'], ORIGIN, True),
    ('other_origin_with_origin_given', 'https://evil.example.com/hasura-api/v1/graphql', ['/hasura-api'], ORIGIN, False),
    ('origin_lookalike', 'https://app.example.com.evil/hasura-api/x', ['/hasura-api'], ORIGIN, False),
    ('absolute_never_matches_path_entry_without_origin', 'https://app.example.com/hasura-api/v1/graphql', ['/hasura-api'], "https://other.example.org", False),
    ('origin_entry_matches_path_under_it', 'https://api.s4hospitality.net/v1/graphql', ['https://api.s4hospitality.net'], ORIGIN, True),
    ('absolute_entry_with_path_boundary_ok', 'https://api.s4hospitality.net/v1/graphql', ['https://api.s4hospitality.net/v1'], ORIGIN, True),
    ('absolute_entry_with_path_boundary_bad', 'https://api.s4hospitality.net/v10/graphql', ['https://api.s4hospitality.net/v1'], ORIGIN, False),
    ("backslash_authority_userinfo", "https://evil.com\\@api.s4hospitality.net/x", ["https://api.s4hospitality.net"], "https://a.b", False),
    ("plain_userinfo_url", "https://user@api.s4hospitality.net/x", ["https://api.s4hospitality.net"], ORIGIN, False),
    ("userinfo_in_entry", "https://api.s4hospitality.net/x", ["https://user@api.s4hospitality.net"], ORIGIN, False),
    ("backslash_in_entry", "https://api.s4hospitality.net/x", ["https://api.s4hospitality.net\\x"], ORIGIN, False),
    ("backslash_in_path_entry", ORIGIN + "/hasura-api/x", ["/hasura-api\\x"], ORIGIN, False),
    ("control_char_in_url", "https://api.s4hospitality.net/x\n", ["https://api.s4hospitality.net"], ORIGIN, False),
    ("tab_in_url", "https://api.s4hospitality.net/\tx", ["https://api.s4hospitality.net"], ORIGIN, False),
]


@pytest.mark.parametrize("url,entries,origin,expected", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_matches_allowlist(url, entries, origin, expected):
    assert matches_allowlist(url, entries, origin) is expected


def test_blank_entries_are_skipped():
    assert matches_allowlist(ORIGIN + "/hasura-api/x", ["  ", "/hasura-api"], ORIGIN) is True
