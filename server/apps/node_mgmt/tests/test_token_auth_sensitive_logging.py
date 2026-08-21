from types import SimpleNamespace

import pytest

from apps.node_mgmt.utils.token_auth import get_client_token
from config.components.drf import AUTH_TOKEN_HEADER_NAME


pytestmark = pytest.mark.unit


def test_malformed_authorization_header_value_is_absent_from_logs(mocker):
    authorization = "Basic malformed-sidecar-secret"
    logger = mocker.patch("apps.node_mgmt.utils.token_auth.logger")
    request = SimpleNamespace(META={AUTH_TOKEN_HEADER_NAME: authorization})

    assert get_client_token(request) is None
    logger.warning.assert_called_once_with(
        "sidecar.authentication_failed failed_stage=%s reason=%s error_type=%s",
        "authorization_parse",
        "malformed_header",
        "Error",
    )
    assert authorization not in repr(logger.mock_calls)
    assert authorization[:20] not in repr(logger.mock_calls)
