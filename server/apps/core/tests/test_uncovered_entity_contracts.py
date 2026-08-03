"""补齐用户认证结果实体的字段约束。"""

import pytest
from pydantic import ValidationError

from apps.core.entities.user_token_entity import UserTokenEntity


pytestmark = pytest.mark.unit


def test_user_token_entity_requires_success_and_keeps_optional_diagnostics():
    success = UserTokenEntity(success=True, token="jwt-token")
    failure = UserTokenEntity(success=False, error_message="expired")

    assert success.model_dump() == {
        "token": "jwt-token",
        "error_message": None,
        "success": True,
    }
    assert failure.error_message == "expired"
    with pytest.raises(ValidationError):
        UserTokenEntity()
