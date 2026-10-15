"""Collector release apply 失败日志不得写入暂存 token。"""

import logging

import pytest

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.node_mgmt.services.collector_release.service import CollectorReleaseService

pytestmark = pytest.mark.unit


def test_apply_unreadable_staging_omits_token_from_logs(mocker, caplog):
    sentinel = "SENTINEL_REL_5952_ZzQ9mK2p"
    mocker.patch(
        "apps.node_mgmt.services.collector_release.service.cache.get",
        return_value={"collector": "nats-collector", "path": "/tmp/missing.zip"},
    )
    mocker.patch("apps.node_mgmt.services.collector_release.service.CollectorReleaseService._acquire_import_lock")
    mocker.patch(
        "apps.node_mgmt.services.collector_release.service.parse_release_path",
        side_effect=OSError("No such file"),
    )
    mocker.patch("apps.node_mgmt.services.collector_release.service.cache.delete")

    with caplog.at_level(logging.WARNING, logger="node"):
        with pytest.raises(ValidationAppException):
            CollectorReleaseService.apply(sentinel)

    assert sentinel not in caplog.text
    assert "unreadable" in caplog.text
