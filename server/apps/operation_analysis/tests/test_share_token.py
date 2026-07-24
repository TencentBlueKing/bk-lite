import uuid

import pytest

from apps.operation_analysis.services.share_token import (
    InvalidShareToken,
    build_share_token,
    parse_share_token,
)


def test_share_token_round_trip_without_row_version(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    public_id = uuid.uuid4()
    assert parse_share_token(build_share_token(public_id)) == public_id
    assert str(public_id) not in build_share_token(public_id)


def test_share_token_is_stable(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    public_id = uuid.uuid4()
    assert build_share_token(public_id) == build_share_token(public_id)


def test_share_token_rejects_tampering(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    token = build_share_token(uuid.uuid4())
    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(InvalidShareToken):
        parse_share_token(token[:-1] + replacement)
