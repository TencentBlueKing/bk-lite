"""CMDB NATS delete_instance 的分发与服务链契约测试。"""

from unittest.mock import patch

import django
import pytest
from asgiref.sync import async_to_sync
from django.conf import settings

django.setup()

from apps.cmdb.nats import nats as cmdb_nats
from nats_client.handlers import nats_handler


@pytest.mark.django_db
def test_delete_instance_nats_dispatch_applies_scope_before_delete():
    """NATS 分发后的授权范围必须进入实例查询，再执行审计和图删除。"""
    instance = {
        "_id": 9,
        "model_id": "host",
        "inst_name": "host-09",
        "organization": [4],
    }

    with (
        patch(
            "apps.cmdb.services.instance.InstanceManage.query_entity_by_ids",
            return_value=[instance],
        ),
        patch(
            "apps.cmdb.services.instance.ModelManage.search_model_info",
            return_value={"model_name": "主机"},
        ),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph_client,
        patch("apps.cmdb.services.instance.batch_create_change_record") as mock_audit,
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension") as mock_extension,
        patch(
            "apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids"
        ) as mock_schedule_sync,
    ):
        graph = mock_graph_client.return_value.__enter__.return_value
        graph.query_entity.return_value = ([instance], 1)

        result = async_to_sync(nats_handler)(
            f"{settings.NATS_NAMESPACE}.{cmdb_nats.delete_instance.__name__}",
            {
                "args": [
                    {
                        "inst_id": 9,
                        "service_scope": {"allowed_org_ids": [4]},
                    }
                ],
                "kwargs": {},
            },
        )

    assert result == {"result": True, "deleted": [9]}
    _, permission_kwargs = graph.query_entity.call_args
    assert {
        "field": "organization",
        "type": "list_any[]",
        "value": [4],
    } in permission_kwargs["params"]
    mock_audit.assert_called_once()
    graph.batch_delete_entity.assert_called_once_with("instance", [9])
    mock_extension.return_value.on_instances_delete.assert_called_once_with([9])
    mock_schedule_sync.assert_called_once_with(["host"])
