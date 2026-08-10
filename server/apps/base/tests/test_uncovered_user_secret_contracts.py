"""补齐 API Secret 空输入和摘要幂等契约。"""

import pytest

from apps.base.models.user import UserAPISecret


pytestmark = pytest.mark.unit


def test_api_secret_empty_and_prehashed_values_are_not_rewritten():
    assert UserAPISecret.hash_api_secret("") == ""
    assert UserAPISecret.find_by_api_secret("") is None

    hashed = UserAPISecret.hash_api_secret("plain-secret")
    assert hashed.startswith(UserAPISecret.HASH_PREFIX)
    assert UserAPISecret.hash_api_secret(hashed) == hashed
    assert UserAPISecret.get_api_secret_preview(
        UserAPISecret(api_secret=hashed)
    ) == "********"
