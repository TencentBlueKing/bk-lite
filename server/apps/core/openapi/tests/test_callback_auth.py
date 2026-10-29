"""网关回调放行：路径命中 callback_paths 即可，不另要共享密钥。"""

import pytest

from apps.core.openapi.views import _FORWARDED_URI_RE, _try_callback_auth

pytestmark = [pytest.mark.unit]

CALLBACK_URI = "/openapi/v1/itsm/openapi/v1/action_components/callback/"
CALLBACK_ENTRY = {"callback_paths": ["/openapi/v1/action_components/callback/"]}


class _Req:
    def __init__(self, uri, acting_user="", acting_team=""):
        self.META = {
            "HTTP_X_FORWARDED_URI": uri,
            "HTTP_X_BKLITE_ACTING_USER": acting_user,
            "HTTP_X_BKLITE_ACTING_TEAM": acting_team,
        }


def test_callback_path_allows_without_secret():
    matched = _FORWARDED_URI_RE.match(CALLBACK_URI)
    identity, ok = _try_callback_auth(
        _Req(CALLBACK_URI, "admin@domain.com", "1"),
        matched,
        CALLBACK_ENTRY,
    )

    assert ok is True
    assert identity.user == "admin"
    assert identity.domain == "domain.com"
    assert identity.team_ids == [1]
    assert identity.credential_type == "callback"


def test_non_callback_path_does_not_skip_api_key():
    uri = "/openapi/v1/itsm/tickets/create"
    matched = _FORWARDED_URI_RE.match(uri)
    identity, ok = _try_callback_auth(_Req(uri), matched, CALLBACK_ENTRY)

    assert ok is False
    assert identity is None


def test_empty_callback_paths_does_not_skip_api_key():
    matched = _FORWARDED_URI_RE.match(CALLBACK_URI)
    identity, ok = _try_callback_auth(_Req(CALLBACK_URI), matched, {"callback_paths": []})

    assert ok is False
    assert identity is None
