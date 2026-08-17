from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.log.models import CollectConfig, CollectInstance, CollectType
from apps.log.views.collect_config import CollectInstanceViewSet


@pytest.mark.django_db
def test_remove_collect_instance_uses_log_scoped_delete(monkeypatch):
    collect_type = CollectType.objects.create(name="file", collector="Vector", icon="file")
    instance = CollectInstance.objects.create(id="log-instance", name="日志实例", collect_type=collect_type)
    config = CollectConfig.objects.create(
        id="log-base-config",
        collect_instance=instance,
        file_type="yaml",
        is_child=False,
    )
    node_mgmt = Mock()
    monkeypatch.setattr("apps.log.views.collect_config.NodeMgmt", lambda: node_mgmt)
    monkeypatch.setattr(
        CollectInstanceViewSet,
        "_authorize_instances",
        lambda _self, _request, _ids: ([instance], None),
    )

    response = CollectInstanceViewSet().remove_collect_instance(
        SimpleNamespace(data={"instance_ids": [instance.id]})
    )

    assert response.status_code == 200
    node_mgmt.delete_configs.assert_called_once_with([config.id], source_app="log")
