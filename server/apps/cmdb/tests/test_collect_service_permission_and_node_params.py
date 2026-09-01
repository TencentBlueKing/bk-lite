"""采集服务：权限守卫、组织规则删除、节点参数推送/删除。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cmdb.services.collect_service import CollectModelService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


def test_has_permission_raises_when_view_denies():
    request = SimpleNamespace(user=SimpleNamespace(username="u"), COOKIES={})
    instance = SimpleNamespace(id=1)
    view = MagicMock()
    view.get_has_permission.return_value = False
    with patch("apps.cmdb.services.collect_service.get_current_team_from_request", return_value=1):
        with pytest.raises(BaseAppException, match="权限"):
            CollectModelService.has_permission(request, instance, view)
    view.get_has_permission.assert_called_once()

    view.get_has_permission.return_value = True
    with patch("apps.cmdb.services.collect_service.get_current_team_from_request", return_value=1):
        CollectModelService.has_permission(request, instance, view)


def test_delete_team_only_removes_dropped_orgs():
    view = MagicMock()
    CollectModelService.delete_team(9, [1, 2, 3], [1], view)
    view.delete_rules.assert_called_once_with(9, [2, 3])


def test_push_and_delete_node_params_call_node_mgmt():
    instance = SimpleNamespace(id=5, is_k8s=False)
    factory = MagicMock()
    factory.get_node_params.return_value.main.return_value = [{"node_id": "n1"}]
    node_mgmt = MagicMock()
    node_mgmt.batch_add_node_child_config.return_value = {"ok": True}
    node_mgmt.delete_child_configs.return_value = {"ok": True}
    with (
        patch("apps.cmdb.services.collect_service.NodeParamsFactory", factory),
        patch("apps.cmdb.services.collect_service.NodeMgmt", return_value=node_mgmt),
    ):
        CollectModelService.push_butch_node_params(instance)
        CollectModelService.delete_butch_node_params(instance)
    factory.get_node_params.assert_called()
    node_mgmt.batch_add_node_child_config.assert_called_once_with([{"node_id": "n1"}])
    node_mgmt.delete_child_configs.assert_called_once()
    factory.get_node_params.return_value.main.assert_any_call(operator="delete")
