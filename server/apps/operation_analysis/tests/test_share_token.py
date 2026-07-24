import uuid

import pytest

from apps.operation_analysis.services.share_token import (
    InvalidShareToken,
    build_share_token,
    parse_share_token,
)


def test_share_token_round_trip(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key"
    public_id = uuid.uuid4()

    token = build_share_token(public_id, 7)

    assert parse_share_token(token) == (public_id, 7)
    assert str(public_id) not in token


def test_share_token_is_stable(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key"
    public_id = uuid.uuid4()

    assert build_share_token(public_id, 1) == build_share_token(public_id, 1)


def test_share_token_rejects_tampering(settings):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key"
    token = build_share_token(uuid.uuid4(), 1)
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(InvalidShareToken):
        parse_share_token(token[:-1] + replacement)

