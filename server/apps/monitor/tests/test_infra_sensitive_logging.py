import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.services.infra import InfraService


pytestmark = pytest.mark.unit


def test_token_value_is_absent_from_lifecycle_logs(mocker):
    token = "monitor-secret-token"
    logger = mocker.patch("apps.monitor.services.infra.logger")
    mocker.patch("apps.monitor.services.infra.uuid.uuid4", return_value=token)
    mocker.patch("apps.monitor.services.infra.cache.set")
    mocker.patch(
        "apps.monitor.services.infra.cache.get",
        return_value={
            "cluster_name": "c1",
            "cloud_region_id": "5",
            "usage_count": 0,
            "max_usage": 5,
        },
    )

    assert InfraService.generate_install_token("c1", "5") == token
    InfraService.validate_and_get_token_data(token)

    assert logger.info.call_args_list[0].args[0].startswith(
        "monitor.infra_install_token.generated"
    )
    assert logger.info.call_args_list[1].args[0].startswith(
        "monitor.infra_install_token.validated"
    )
    assert token not in repr(logger.mock_calls)
    assert token[:8] not in repr(logger.mock_calls)


def test_invalid_token_value_is_absent_from_warning(mocker):
    token = "monitor-invalid-secret"
    logger = mocker.patch("apps.monitor.services.infra.logger")
    mocker.patch("apps.monitor.services.infra.cache.get", return_value=None)

    with pytest.raises(BaseAppException):
        InfraService.validate_and_get_token_data(token)

    assert logger.warning.call_args.args[:2] == (
        "monitor.infra_install_token.validation_failed reason=%s "
        "expires_in_seconds=%s",
        "missing_or_expired",
    )
    assert token not in repr(logger.mock_calls)
    assert token[:8] not in repr(logger.mock_calls)
