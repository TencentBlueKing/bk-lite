"""
CMDB CQL查询测试类

使用方式:
1. 在Django shell中使用:
   python manage.py shell
   >>> from apps.cmdb.tests import CQLQueryTest
   >>> test = CQLQueryTest()
   >>> result = test.query("MATCH (n) RETURN n LIMIT 10")

2. 如果需要直接运行此文件,请确保已设置Django环境:
   import os
   import django
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
   django.setup()
"""

import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.core.exceptions.base_app_exception import BaseAppException

# 检查是否在Django环境中
if __name__ == "__main__":
    # 添加项目根目录到Python路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 初始化Django环境
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    import django

    django.setup()

from apps.cmdb.constants.constants import PERMISSION_INSTANCES, VIEW
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.collect_tool_service import CollectToolService
from apps.cmdb.utils.permission_util import DENY_PERMISSION_PLACEHOLDER, CmdbRulesFormatUtil
from apps.core.logger import cmdb_logger as logger


def _make_cmdb_request(username="alice", groups=None):
    groups = groups or [{"id": 1}]
    return SimpleNamespace(
        user=SimpleNamespace(
            username=username,
            group_list=groups,
            group_tree=[],
            roles=[],
            permission={"asset_info-View"},
            is_superuser=False,
            locale="zh-Hans",
        ),
        COOKIES={"current_team": str(groups[0]["id"]), "include_children": "0"},
        api_pass=False,
    )


def _make_instance(inst_id=1001, creator="bob", organizations=None):
    return {
        "_id": inst_id,
        "model_id": "host",
        "inst_name": f"host-{inst_id}",
        "organization": organizations or [1],
        "_creator": creator,
    }


def _make_topology_node(inst_id, inst_name, model_id="host", children=None, **extra):
    node = {
        "_id": inst_id,
        "model_id": model_id,
        "inst_name": inst_name,
        "children": children or [],
    }
    node.update(extra)
    return node


def _topology_child_ids(node):
    return [child.get("_id") for child in (node or {}).get("children", [])]


def _response_json(response):
    return json.loads(response.content)


class _DummyAtomic:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_import_model_config_applies_shared_post_import_extras():
    from apps.cmdb.services.model import ModelManage

    fake_file = MagicMock()
    fake_model_config = {"attr-host": [{"attr_id": "inst_name"}], "asso-host": []}

    with (
        patch("apps.cmdb.model_migrate.migrete_service.ModelMigrate") as mock_migrator_cls,
        patch.object(ModelManage, "_apply_model_config_post_import_extras") as mock_apply_extras,
    ):
        mock_migrator = MagicMock()
        mock_migrator.model_config = fake_model_config
        mock_migrator.main.return_value = {"ok": True}
        mock_migrator_cls.return_value = mock_migrator

        result = ModelManage.import_model_config(fake_file)

        mock_migrator_cls.assert_called_once_with(file_source=fake_file, is_pre=False)
        mock_migrator.main.assert_called_once_with()
        mock_apply_extras.assert_called_once_with(fake_model_config)
        assert result == {"ok": True}


def test_model_init_reuses_shared_post_import_extras():
    with (
        patch("apps.cmdb.management.commands.model_init.ModelMigrate") as mock_migrator_cls,
        patch("apps.cmdb.management.commands.model_init.ModelManage._apply_model_config_post_import_extras") as mock_apply_extras,
    ):
        mock_migrator = MagicMock()
        mock_migrator.model_config = {"attr-host": []}
        mock_migrator.main.return_value = {"ok": True}
        mock_migrator_cls.return_value = mock_migrator

        from django.core.management import call_command

        call_command("model_init")

        mock_migrator_cls.assert_called_once_with()
        mock_migrator.main.assert_called_once_with()
        mock_apply_extras.assert_called_once_with(mock_migrator.model_config)


def test_instance_association_instance_list_denies_user_without_object_permission():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    instance = _make_instance()

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=instance,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
            return_value=False,
        ) as mock_check_permission,
        patch("apps.cmdb.views.instance.InstanceManage.instance_association_instance_list") as mock_association_list,
    ):
        response = InstanceViewSet().instance_association_instance_list(
            request,
            "host",
            1001,
        )

    assert response.status_code == 403
    assert _response_json(response)["result"] is False
    mock_check_permission.assert_called_once()
    mock_association_list.assert_not_called()


def test_topo_search_denies_user_without_object_permission():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    instance = _make_instance()

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=instance,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
            return_value=False,
        ) as mock_check_permission,
        patch("apps.cmdb.views.instance.InstanceManage.topo_search_lite") as mock_topo_search,
    ):
        response = InstanceViewSet().topo_search(request, "host", 1001)

    assert response.status_code == 403
    assert _response_json(response)["result"] is False
    mock_check_permission.assert_called_once_with(request, instance, VIEW)
    mock_topo_search.assert_not_called()


def test_topo_search_filters_unauthorized_neighbors_from_response():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    center = _make_instance(inst_id=1001)
    visible_child = _make_instance(inst_id=1002)
    hidden_child = _make_instance(inst_id=1003, organizations=[2])
    topology = {
        "src_result": _make_topology_node(
            1001,
            "host-1001",
            children=[
                _make_topology_node(1002, "host-1002", children=[]),
                _make_topology_node(1003, "secret-host", children=[]),
            ],
        ),
        "dst_result": _make_topology_node(1001, "host-1001", children=[]),
    }

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=center,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
            return_value=True,
        ) as mock_check_permission,
        patch(
            "apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions",
            return_value={1: {"inst_names": ["host-1002"], "permission_instances_map": {"host-1002": ["View"]}}},
        ) as mock_permissions,
        patch(
            "apps.cmdb.services.instance.InstanceManage._query_instance_map_by_ids",
            return_value={1001: center, 1002: visible_child, 1003: hidden_child},
        ),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph_client,
    ):
        graph_context = MagicMock()
        graph_context.__enter__.return_value.query_topo_lite.return_value = topology
        graph_context.__exit__.return_value = False
        mock_graph_client.return_value = graph_context
        response = InstanceViewSet().topo_search(request, "host", 1001)

    payload = _response_json(response)
    assert response.status_code == 200
    assert payload["data"]["src_result"]["inst_name"] == "host-1001"
    assert _topology_child_ids(payload["data"]["src_result"]) == [1002]
    assert "secret-host" not in json.dumps(payload["data"], ensure_ascii=False)
    mock_check_permission.assert_called_once_with(request, center, VIEW)
    mock_permissions.assert_called_once_with(request=request, model_id="host")


def test_topo_search_expand_filters_reintroduced_unauthorized_nodes():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    center = _make_instance(inst_id=1001)
    visible_child = _make_instance(inst_id=1002)
    hidden_grandchild = _make_instance(inst_id=1004, organizations=[2])
    topology = {
        "src_result": _make_topology_node(
            1001,
            "host-1001",
            children=[
                _make_topology_node(
                    1002,
                    "host-1002",
                    children=[_make_topology_node(1004, "hidden-child")],
                )
            ],
        ),
        "dst_result": _make_topology_node(1001, "host-1001", children=[]),
    }

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=center,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
            return_value=True,
        ) as mock_check_permission,
        patch(
            "apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions",
            return_value={1: {"inst_names": ["host-1002"], "permission_instances_map": {"host-1002": ["View"]}}},
        ) as mock_permissions,
        patch(
            "apps.cmdb.services.instance.InstanceManage._query_instance_map_by_ids",
            return_value={1001: center, 1002: visible_child, 1004: hidden_grandchild},
        ),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph_client,
    ):
        graph_context = MagicMock()
        graph_context.__enter__.return_value.query_topo_lite.return_value = topology
        graph_context.__exit__.return_value = False
        mock_graph_client.return_value = graph_context
        expand_request = SimpleNamespace(
            **request.__dict__,
            data={"inst_id": 1001, "parent_id": [1001, 1002]},
        )
        response = InstanceViewSet().topo_search_expand_post(expand_request)

    payload = _response_json(response)
    assert response.status_code == 200
    assert _topology_child_ids(payload["data"]["src_result"]) == [1002]
    assert payload["data"]["src_result"]["children"][0]["children"] == []
    assert "hidden-child" not in json.dumps(payload["data"], ensure_ascii=False)
    mock_check_permission.assert_called_once_with(expand_request, center, VIEW)
    mock_permissions.assert_called_once_with(request=expand_request, model_id="host")


def test_instance_manage_topology_filter_preserves_authorized_topology():
    from apps.cmdb.services.instance import InstanceManage

    center = _make_instance(inst_id=1001)
    visible_child = _make_instance(inst_id=1002)
    topology = {
        "src_result": _make_topology_node(1001, "host-1001", children=[_make_topology_node(1002, "host-1002")]),
        "dst_result": _make_topology_node(1001, "host-1001", children=[]),
    }

    with patch.object(
        InstanceManage,
        "_query_instance_map_by_ids",
        return_value={1001: center, 1002: visible_child},
    ):
        filtered = InstanceManage._filter_topology_result(
            topology,
            center_id=1001,
            permission_map={1: {"inst_names": [], "permission_instances_map": {}}},
            user=SimpleNamespace(username="alice"),
        )

    assert filtered == topology


def test_instance_association_map_batches_graph_queries_by_direction():
    from apps.cmdb.services.instance import InstanceManage

    src_edges = [
        {
            "src_inst_id": 101,
            "dst_inst_id": 201,
            "src_model_id": "host",
            "dst_model_id": "service",
        },
        {
            "src_inst_id": 102,
            "dst_inst_id": 202,
            "src_model_id": "host",
            "dst_model_id": "service",
        },
    ]
    dst_edges = [
        {
            "src_inst_id": 301,
            "dst_inst_id": 102,
            "src_model_id": "service",
            "dst_model_id": "host",
        }
    ]

    graph_client = MagicMock()
    graph_client.query_edge.side_effect = [src_edges, dst_edges]

    graph_context = MagicMock()
    graph_context.__enter__.return_value = graph_client
    graph_context.__exit__.return_value = False

    with patch(
        "apps.cmdb.services.instance.GraphClient",
        return_value=graph_context,
    ):
        relation_map = InstanceManage.instance_association_map(
            model_id="host",
            inst_ids=[101, 102],
            related_model="service",
        )

    assert relation_map == {101: [201], 102: [202, 301]}
    assert graph_client.query_edge.call_count == 2
    src_call, dst_call = graph_client.query_edge.call_args_list
    assert src_call.args[0] == "instance_association"
    assert src_call.args[1] == [
        {"field": "src_inst_id", "type": "int[]", "value": [101, 102]},
        {"field": "src_model_id", "type": "str=", "value": "host"},
        {"field": "dst_model_id", "type": "str=", "value": "service"},
    ]
    assert dst_call.args[0] == "instance_association"
    assert dst_call.args[1] == [
        {"field": "dst_inst_id", "type": "int[]", "value": [101, 102]},
        {"field": "dst_model_id", "type": "str=", "value": "host"},
        {"field": "src_model_id", "type": "str=", "value": "service"},
    ]


def test_check_instances_permission_limits_query_to_target_instance_ids():
    from apps.cmdb.services.instance import InstanceManage

    instances = [
        {"_id": 101, "inst_name": "host-101"},
        {"_id": 102, "inst_name": "host-102"},
    ]

    graph_client = MagicMock()
    graph_client.query_entity.return_value = (instances, None)

    graph_context = MagicMock()
    graph_context.__enter__.return_value = graph_client
    graph_context.__exit__.return_value = False

    with (
        patch(
            "apps.cmdb.services.instance.InstanceManage.get_permission_params",
            return_value=[{"field": "organization", "type": "list_any[]", "value": [1]}],
        ),
        patch(
            "apps.cmdb.services.instance.GraphClient",
            return_value=graph_context,
        ),
    ):
        InstanceManage.check_instances_permission(
            instances=instances,
            model_id="host",
            user_groups=[{"id": 1}],
            roles=[],
        )

    graph_client.query_entity.assert_called_once_with(
        label="instance",
        params=[
            {"field": "model_id", "type": "str=", "value": "host"},
            {"field": "id", "type": "id[]", "value": [101, 102]},
            {"field": "organization", "type": "list_any[]", "value": [1]},
        ],
    )


def test_falkordb_entity_count_applies_base_params_before_grouping():
    from apps.cmdb.graph.falkordb import FalkorDBClient

    client = FalkorDBClient.__new__(FalkorDBClient)
    client.ENABLE_PARAMETERIZATION = False
    client._param_collector = None
    client._execute_query = MagicMock(
        return_value=SimpleNamespace(
            header=[("", "os_type"), ("", "count")],
            result_set=[["1", 2]],
        )
    )

    result = client.entity_count(
        label="instance",
        group_by_attr="os_type",
        params=[{"field": "model_id", "type": "str=", "value": "host"}],
        format_permission_dict={1: []},
    )

    assert result == {"1": 2}
    sql = client._execute_query.call_args.args[0]
    assert "model_id" in sql
    assert "organization" in sql
    assert "COUNT(n) AS count" in sql


def test_group_inst_count_passes_base_params_and_permission_scope_to_graph_client():
    from apps.cmdb.services.instance import InstanceManage

    graph_client = MagicMock()
    graph_client.entity_count.return_value = {"host": 3}

    graph_context = MagicMock()
    graph_context.__enter__.return_value = graph_client
    graph_context.__exit__.return_value = False

    with patch("apps.cmdb.services.instance.GraphClient", return_value=graph_context):
        result = InstanceManage.group_inst_count(
            group_by_attr="model_id",
            permissions_map={1: {"inst_names": ["host-1", "host-2"], "permission_instances_map": {}}},
            params=[{"field": "model_id", "type": "str=", "value": "host"}],
            creator="alice",
        )

    assert result == {"host": 3}
    graph_client.entity_count.assert_called_once_with(
        label="instance",
        group_by_attr="model_id",
        params=[{"field": "model_id", "type": "str=", "value": "host"}],
        format_permission_dict={
            1: [
                {"field": "inst_name", "type": "str[]", "value": ["host-1", "host-2"]},
                {"field": "_creator", "type": "str=", "value": "alice"},
            ]
        },
    )


def test_get_instance_group_by_uses_graph_aggregation_for_enum_field():
    from apps.cmdb.nats.nats import get_instance_group_by

    with (
        patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value={1: {"inst_names": [], "permission_instances_map": {}}}),
        patch(
            "apps.cmdb.nats.nats.ModelManage.search_model_attr",
            return_value=[
                {
                    "attr_id": "os_type",
                    "attr_type": "enum",
                    "enum_select_mode": "single",
                    "option": [{"id": 1, "name": "Linux"}],
                }
            ],
        ),
        patch("apps.cmdb.nats.nats.GraphClient") as mock_graph_client,
        patch("apps.cmdb.nats.nats.InstanceManage.group_inst_count", return_value={"1": 2, None: 1}) as mock_group_inst_count,
    ):
        result = get_instance_group_by(model_id="host", field="os_type", user_info={"team": 1, "user": "alice"})

    assert result == {
        "result": True,
        "data": [
            {"name": "Linux", "value": 2},
            {"name": "unknown", "value": 1},
        ],
        "message": "",
    }
    mock_graph_client.assert_not_called()
    mock_group_inst_count.assert_called_once_with(
        group_by_attr="os_type",
        permissions_map={1: {"inst_names": [], "permission_instances_map": {}}},
        params=[{"field": "model_id", "type": "str=", "value": "host"}],
    )


def test_get_instance_group_by_falls_back_to_raw_enum_values_when_display_may_be_missing():
    from apps.cmdb.nats.nats import get_instance_group_by

    with (
        patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value={1: {"inst_names": [], "permission_instances_map": {}}}),
        patch(
            "apps.cmdb.nats.nats.ModelManage.search_model_attr",
            return_value=[
                {
                    "attr_id": "os_type",
                    "attr_type": "enum",
                    "enum_select_mode": "single",
                    "option": [{"id": 1, "name": "Linux"}, {"id": "other", "name": "Other"}],
                }
            ],
        ),
        patch("apps.cmdb.nats.nats.InstanceManage.group_inst_count", return_value={"1": 2, "other": 1, None: 1}) as mock_group_inst_count,
    ):
        result = get_instance_group_by(model_id="host", field="os_type", user_info={"team": 1, "user": "alice"})

    assert result == {
        "result": True,
        "data": [
            {"name": "Linux", "value": 2},
            {"name": "Other", "value": 1},
            {"name": "unknown", "value": 1},
        ],
        "message": "",
    }
    mock_group_inst_count.assert_called_once_with(
        group_by_attr="os_type",
        permissions_map={1: {"inst_names": [], "permission_instances_map": {}}},
        params=[{"field": "model_id", "type": "str=", "value": "host"}],
    )


def test_falkordb_count_formatter_normalizes_list_keys():
    from apps.cmdb.graph.falkordb_format import FormatDBResult

    result = FormatDBResult(SimpleNamespace(result_set=[[["1"], 2]], header=[])).to_result_of_count()

    assert result == {"1": 2}


def test_get_relation_instances_falls_back_to_per_instance_when_batch_query_fails():
    from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService

    rule = SimpleNamespace(
        id=1,
        model_id="host",
        trigger_types=["relation_change"],
        trigger_config={"relation_change": {"related_model": "service", "fields": []}},
        snapshot_data={},
    )

    with (
        patch(
            "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
            return_value={"model_name": "主机"},
        ),
        patch(
            "apps.cmdb.services.subscription_trigger.InstanceManage.instance_association_map",
            side_effect=RuntimeError("graph timeout"),
        ),
        patch(
            "apps.cmdb.services.subscription_trigger.InstanceManage.instance_association",
            side_effect=[
                [
                    {
                        "src_model_id": "host",
                        "src_inst_id": 101,
                        "dst_model_id": "service",
                        "dst_inst_id": 201,
                    }
                ],
                RuntimeError("single query failed"),
            ],
        ),
    ):
        service = SubscriptionTriggerService(rule)
        relation_map, failed_instance_ids = service._get_relation_instances([101, 102], "service")

    assert relation_map == {101: [201]}
    assert failed_instance_ids == {102}


def test_relation_snapshot_preserves_previous_relations_for_failed_instances():
    from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService

    now = datetime.now()
    rule = SimpleNamespace(
        id=1,
        model_id="host",
        trigger_types=["relation_change"],
        trigger_config={"relation_change": {"related_model": "service", "fields": []}},
        snapshot_data={"relations": {"101": {"service": [201]}}},
        last_check_time=now,
        created_at=now,
    )
    instances = [{"_id": 101, "inst_name": "host-101"}]

    with (
        patch(
            "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
            return_value={"model_name": "主机"},
        ),
        patch.object(
            SubscriptionTriggerService,
            "_build_related_change_map",
            return_value=({}, 0),
        ),
        patch.object(
            SubscriptionTriggerService,
            "_build_related_inst_name_map",
            return_value={},
        ),
    ):
        service = SubscriptionTriggerService(rule)
        current_snapshot = service._build_current_snapshot(
            instances,
            relations_by_model={"service": {}},
            failed_relation_instance_ids_by_model={"service": {101}},
        )
        events = service._check_relation_change(
            current_snapshot,
            instances,
            now,
            failed_relation_instance_ids_by_model={"service": {101}},
        )

    assert current_snapshot["relations"] == {"101": {"service": [201]}}
    assert events == []


def test_relation_snapshot_skips_unknown_relations_when_no_previous_snapshot_exists():
    from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService

    now = datetime.now()
    rule = SimpleNamespace(
        id=1,
        model_id="host",
        trigger_types=["relation_change"],
        trigger_config={"relation_change": {"related_model": "service", "fields": []}},
        snapshot_data={},
        last_check_time=now,
        created_at=now,
    )
    instances = [{"_id": 101, "inst_name": "host-101"}]

    with (
        patch(
            "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
            return_value={"model_name": "主机"},
        ),
        patch.object(
            SubscriptionTriggerService,
            "_build_related_change_map",
            return_value=({}, 0),
        ),
        patch.object(
            SubscriptionTriggerService,
            "_build_related_inst_name_map",
            return_value={},
        ),
    ):
        service = SubscriptionTriggerService(rule)
        current_snapshot = service._build_current_snapshot(
            instances,
            relations_by_model={"service": {}},
            failed_relation_instance_ids_by_model={"service": {101}},
        )
        events = service._check_relation_change(
            current_snapshot,
            instances,
            now,
            failed_relation_instance_ids_by_model={"service": {101}},
        )

    assert current_snapshot["relations"] == {"101": {}}
    assert events == []


def test_relation_change_build_related_change_map_short_circuits_when_related_ids_empty():
    from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService

    now = datetime.now()
    rule = SimpleNamespace(
        id=1,
        name="rule-1",
        model_id="host",
        trigger_types=["relation_change"],
        trigger_config={"relation_change": {"related_model": "service", "fields": []}},
        snapshot_data={},
        last_check_time=now,
        created_at=now,
    )

    with patch(
        "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
        return_value={"model_name": "主机"},
    ):
        service = SubscriptionTriggerService(rule)

    result = service._build_related_change_map(
        related_model="service",
        related_instance_ids=[],
        watch_fields=set(),
        checkpoint=now,
    )

    assert result == ({}, 0)


def test_relation_change_build_related_change_map_scopes_query_to_related_instance_ids():
    from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService

    now = datetime.now()
    rule = SimpleNamespace(
        id=1,
        name="rule-1",
        model_id="host",
        trigger_types=["relation_change"],
        trigger_config={"relation_change": {"related_model": "service", "fields": ["status"]}},
        snapshot_data={},
        last_check_time=now,
        created_at=now,
    )
    record = SimpleNamespace(
        inst_id=201,
        before_data={"status": "old"},
        after_data={"status": "new"},
    )

    with (
        patch(
            "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
            return_value={"model_name": "主机"},
        ),
        patch("apps.cmdb.services.subscription_trigger.ChangeRecord.objects.filter") as mock_filter,
    ):
        mock_filter.return_value.order_by.return_value = [record]
        service = SubscriptionTriggerService(rule)
        result = service._build_related_change_map(
            related_model="service",
            related_instance_ids=[201, 202],
            watch_fields={"status"},
            checkpoint=now,
        )

    assert result == ({201: ["字段变化: status: old → new"]}, 1)
    _, kwargs = mock_filter.call_args
    assert kwargs["model_id"] == "service"
    assert kwargs["inst_id__in"] == [201, 202]


def test_relation_change_scopes_related_ids_from_previous_and_current_snapshots():
    from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService

    now = datetime.now()
    rule = SimpleNamespace(
        id=1,
        name="rule-1",
        model_id="host",
        trigger_types=["relation_change"],
        trigger_config={"relation_change": {"related_model": "service", "fields": []}},
        snapshot_data={"relations": {"101": {"service": [201]}, "102": {"service": [202]}}},
        last_check_time=now,
        created_at=now,
    )
    instances = [{"_id": 101, "inst_name": "host-101"}, {"_id": 102, "inst_name": "host-102"}]
    current_snapshot = {"relations": {"101": {"service": [203]}, "102": {"service": [202]}}}

    with (
        patch(
            "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
            return_value={"model_name": "主机"},
        ),
        patch.object(
            SubscriptionTriggerService,
            "_build_related_change_map",
            return_value=({}, 0),
        ) as mock_change_map,
        patch.object(
            SubscriptionTriggerService,
            "_build_related_inst_name_map",
            return_value={},
        ),
    ):
        service = SubscriptionTriggerService(rule)
        service._check_relation_change(current_snapshot, instances, now)

    assert mock_change_map.call_count == 1
    assert mock_change_map.call_args.kwargs["related_instance_ids"] == [201, 202, 203]


def test_relation_change_ignores_unrelated_changes_but_keeps_add_remove_events():
    from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService

    now = datetime.now()
    rule = SimpleNamespace(
        id=1,
        name="rule-1",
        model_id="host",
        trigger_types=["relation_change"],
        trigger_config={"relation_change": {"related_model": "service", "fields": ["status"]}},
        snapshot_data={"relations": {"101": {"service": [201]}}},
        last_check_time=now,
        created_at=now,
    )
    instances = [{"_id": 101, "inst_name": "host-101"}]
    current_snapshot = {"relations": {"101": {"service": [202]}}}

    with (
        patch(
            "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
            return_value={"model_name": "主机"},
        ),
        patch.object(
            SubscriptionTriggerService,
            "_build_related_change_map",
            return_value=({}, 0),
        ),
        patch.object(
            SubscriptionTriggerService,
            "_build_related_inst_name_map",
            return_value={201: "svc-201", 202: "svc-202"},
        ),
    ):
        service = SubscriptionTriggerService(rule)
        events = service._check_relation_change(current_snapshot, instances, now)

    assert len(events) == 1
    summary = events[0].change_summary
    assert "关联模型[service]变化:" in summary
    assert "新增关联: [202]" in summary
    assert "删除关联: [201]" in summary


def test_collect_model_viewset_scopes_detail_queryset_by_permission():
    from apps.cmdb.views.collect import CollectModelViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    view = CollectModelViewSet()
    view.request = request
    view.action = "info"

    filtered_queryset = MagicMock(name="filtered_queryset")

    with patch.object(
        CollectModelViewSet,
        "get_queryset_by_permission",
        return_value=filtered_queryset,
    ) as mock_get_queryset_by_permission:
        result = view.get_queryset()

    assert result is filtered_queryset
    mock_get_queryset_by_permission.assert_called_once()
    call_request, call_queryset = mock_get_queryset_by_permission.call_args.args
    assert call_request is request
    assert call_queryset.model is view.queryset.model


def test_collect_model_instances_uses_permission_filtered_queryset():
    from apps.cmdb.views.collect import CollectModelViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    request.GET = SimpleNamespace(dict=lambda: {"task_type": "host"})
    view = CollectModelViewSet()

    authorized_queryset = MagicMock(name="authorized_queryset")
    filtered_queryset = MagicMock(name="filtered_queryset")
    authorized_queryset.filter.return_value = filtered_queryset
    filtered_queryset.values_list.return_value = [
        [{"_id": 1001, "inst_name": "host-a"}],
    ]

    with patch.object(
        CollectModelViewSet,
        "get_queryset_by_permission",
        return_value=authorized_queryset,
    ) as mock_get_queryset_by_permission:
        response = view.model_instances(request)

    payload = json.loads(response.content)
    assert payload["result"] is True
    assert payload["data"] == [{"id": 1001, "inst_name": "host-a"}]
    mock_get_queryset_by_permission.assert_called_once()
    call_request, call_queryset = mock_get_queryset_by_permission.call_args.args
    assert call_request is request
    assert call_queryset.model is view.queryset.model
    authorized_queryset.filter.assert_called_once()


def test_build_region_query_credential_uses_authorized_task_lookup():
    from apps.cmdb.views.collect import CollectModelViewSet

    request = _make_cmdb_request()
    task = SimpleNamespace(
        decrypt_credentials={"secret_key": "value"},
        driver_type="qcloud",
    )
    params_cls = MagicMock()
    params_cls.build_region_credential.return_value = {"region_secret": "ok"}
    view = CollectModelViewSet()

    with (
        patch.object(
            CollectModelViewSet,
            "_get_authorized_task",
            return_value=task,
        ) as mock_get_authorized_task,
        patch(
            "apps.cmdb.views.collect.NodeParamsFactory.get_params_class",
            return_value=params_cls,
        ) as mock_get_params_class,
    ):
        credential = view._build_region_query_credential(
            request,
            {"model_id": "qcloud_account", "driver_type": "ignored"},
            task_id=42,
        )

    assert credential["model_id"] == "qcloud"
    assert credential["region_secret"] == "ok"
    mock_get_authorized_task.assert_called_once_with(request, 42)
    mock_get_params_class.assert_called_once_with("qcloud", "qcloud")


def test_aliyun_account_protocol_model_plugin_name_falls_back_to_normalized_model_id():
    from apps.cmdb.node_configs.cloud.aliyun import AliyunNodeParams

    instance = SimpleNamespace(
        model_id="aliyun_account",
        driver_type="protocol",
        decrypt_credentials={},
        params={},
        timeout=60,
    )

    node = AliyunNodeParams(instance)

    assert node.model_plugin_name == "aliyun_info"


def test_aliyun_node_params_uses_secret_field_names_for_stargazer():
    from apps.cmdb.node_configs.cloud.aliyun import AliyunNodeParams

    instance = SimpleNamespace(
        id=281,
        model_id="aliyun_account",
        driver_type="protocol",
        decrypt_credentials={
            "accessKey": "ak",
            "accessSecret": "sk",
            "regions": {"resource_id": "cn-guangzhou"},
        },
        params={},
        timeout=300,
    )

    node = AliyunNodeParams(instance)

    assert node.set_credential() == {
        "secret_id": "${PASSWORD_secret_id_cmdb_281}",
        "secret_key": "${PASSWORD_secret_key_cmdb_281}",
        "region_id": "cn-guangzhou",
    }
    assert node.env_config() == {
        "PASSWORD_secret_id_cmdb_281": "ak",
        "PASSWORD_secret_key_cmdb_281": "sk",
    }


def test_collect_model_viewset_hides_system_tasks_from_default_list_queries():
    from apps.cmdb.views.collect import CollectModelViewSet
    from apps.core.utils.viewset_utils import AuthViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    view = CollectModelViewSet()
    view.request = request
    view.action = "list"

    filtered_queryset = MagicMock(name="filtered_queryset")
    visible_queryset = MagicMock(name="visible_queryset")
    filtered_queryset.filter.return_value = visible_queryset

    with patch.object(
        AuthViewSet,
        "get_queryset",
        return_value=filtered_queryset,
    ):
        result = view.get_queryset()

    assert result is visible_queryset
    filtered_queryset.filter.assert_called_once_with(is_visible=True)


def test_collect_task_names_excludes_hidden_system_tasks():
    from apps.cmdb.views.collect import CollectModelViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    view = CollectModelViewSet()

    authorized_queryset = MagicMock(name="authorized_queryset")
    visible_queryset = MagicMock(name="visible_queryset")
    authorized_queryset.filter.return_value = visible_queryset
    visible_queryset.order_by.return_value = visible_queryset
    visible_queryset.values.return_value = []

    with patch.object(
        CollectModelViewSet,
        "get_queryset_by_permission",
        return_value=authorized_queryset,
    ):
        response = view.collect_task_names(request)

    assert response.status_code == 200
    authorized_queryset.filter.assert_called_once_with(is_visible=True)
    visible_queryset.order_by.assert_called_once_with("id")


def test_task_status_excludes_hidden_system_tasks_from_statistics():
    from apps.cmdb.views.collect import CollectModelViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    view = CollectModelViewSet()
    view.request = request
    view.action = "task_status"

    filtered_queryset = MagicMock(name="filtered_queryset")
    visible_queryset = MagicMock(name="visible_queryset")
    only_queryset = MagicMock(name="only_queryset")
    filtered_queryset.filter.return_value = visible_queryset
    visible_queryset.only.return_value = only_queryset

    with (
        patch.object(CollectModelViewSet, "get_queryset", return_value=filtered_queryset),
        patch.object(CollectModelViewSet, "get_queryset_by_permission", return_value=filtered_queryset),
        patch("apps.cmdb.views.collect.CollectModelIdStatusSerializer") as mock_serializer,
    ):
        mock_serializer.return_value.data = []
        response = view.task_status(request)

    assert response.status_code == 200
    filtered_queryset.filter.assert_called_once_with(is_visible=True)
    visible_queryset.only.assert_called_once_with("model_id", "driver_type", "exec_status")


def test_task_status_splits_same_model_by_driver_type():
    from apps.cmdb.views.collect import CollectModelViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    view = CollectModelViewSet()
    view.request = request
    view.action = "task_status"

    filtered_queryset = MagicMock(name="filtered_queryset")
    visible_queryset = MagicMock(name="visible_queryset")
    only_queryset = MagicMock(name="only_queryset")
    filtered_queryset.filter.return_value = visible_queryset
    visible_queryset.only.return_value = only_queryset

    serializer_rows = [
        {"model_id": "physcial_server", "driver_type": "job", "exec_status": "success"},
        {"model_id": "physcial_server", "driver_type": "protocol", "exec_status": "running"},
    ]

    with (
        patch.object(CollectModelViewSet, "get_queryset", return_value=filtered_queryset),
        patch.object(CollectModelViewSet, "get_queryset_by_permission", return_value=filtered_queryset),
        patch("apps.cmdb.views.collect.CollectModelIdStatusSerializer") as mock_serializer,
    ):
        mock_serializer.return_value.data = serializer_rows
        response = view.task_status(request)

    payload = _response_json(response)
    assert payload["result"] is True
    assert payload["data"] == {
        "physcial_server__job": {"success": 1, "failed": 0, "running": 0},
        "physcial_server__protocol": {"success": 0, "failed": 0, "running": 1},
    }


def test_collect_model_service_allows_node_mgmt_empty_value_credential():
    from apps.cmdb.services.collect_service import CollectModelService

    instance = SimpleNamespace(
        is_k8s=False,
        decrypt_credentials={"password": "old", "username": "old", "port": 22},
        params={"source": "node_mgmt_sync"},
    )
    data = {
        "credential": {"password": "", "username": "", "port": 22},
        "params": {"source": "node_mgmt_sync"},
    }

    CollectModelService.format_update_credential(instance, data)

    assert data["credential"] == {"password": "", "username": "", "port": 22}


def test_collect_model_service_requires_credential_for_non_system_tasks():
    from apps.cmdb.services.collect_service import CollectModelService
    from apps.core.exceptions.base_app_exception import BaseAppException

    instance = SimpleNamespace(is_k8s=False, decrypt_credentials={}, params={})
    data = {"credential": {}, "params": {}}

    try:
        CollectModelService.format_update_credential(instance, data)
    except BaseAppException as err:
        assert str(err) == "采集凭据不能为空！"
    else:
        raise AssertionError("Expected BaseAppException")


def test_collect_model_service_get_cloud_region_id_by_node_uses_rpc():
    from apps.cmdb.services.collect_service import CollectModelService

    node_mgmt = MagicMock()
    node_mgmt.get_nodes_by_ids.return_value = [{"id": "node-1", "cloud_region_id": 12, "cloud_region_name": "gz"}]

    with patch("apps.cmdb.services.collect_service.NodeMgmt", return_value=node_mgmt):
        result = CollectModelService._get_cloud_region_id_by_node("node-1")

    assert result == 12
    node_mgmt.get_nodes_by_ids.assert_called_once_with(["node-1"])


def test_collect_unique_rule_conflicts_detects_batch_duplicates_without_crashing():
    from apps.cmdb.services.unique_rule import ModelUniqueRule, collect_unique_rule_conflicts

    rules = [ModelUniqueRule(rule_id="rule-ip-cloud", order=1, field_ids=["ip_addr", "cloud"])]
    items = [
        {"inst_name": "host-1", "ip_addr": "127.0.0.2", "cloud": 1},
        {"inst_name": "host-2", "ip_addr": "127.0.0.2", "cloud": 1},
    ]
    attrs_by_id = {
        "ip_addr": {"attr_name": "IP"},
        "cloud": {"attr_name": "云区域"},
    }

    conflicts = collect_unique_rule_conflicts(
        rules=rules,
        items=items,
        exist_items=[],
        attrs_by_id=attrs_by_id,
    )

    assert len(conflicts) == 1
    assert conflicts[0].field_ids == ["ip_addr", "cloud"]
    assert conflicts[0].field_values == {"ip_addr": "127.0.0.2", "cloud": 1}
    assert "与本批次数据冲突" in conflicts[0].message


def test_collect_model_service_get_cloud_region_name_uses_rpc():
    from apps.cmdb.services.collect_service import CollectModelService

    node_mgmt = MagicMock()
    node_mgmt.cloud_region_list.return_value = [{"id": 1, "name": "default"}, {"id": 12, "name": "gz"}]

    with patch("apps.cmdb.services.collect_service.NodeMgmt", return_value=node_mgmt):
        result = CollectModelService._get_cloud_region_name(12)

    assert result == "gz"
    node_mgmt.cloud_region_list.assert_called_once_with()


def test_node_mgmt_sync_service_updates_config_and_periodic_tasks():
    from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    config = MagicMock(spec=NodeMgmtSyncConfig)
    config.id = 1
    config.name = "节点管理同步"
    config.is_builtin = True
    config.auto_sync_enabled = False
    config.auto_collect_enabled = False
    config.sync_interval_minutes = 30
    config.collect_interval_minutes = 30

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=config),
        patch("apps.cmdb.services.node_mgmt_sync_service.transaction.atomic", return_value=_DummyAtomic()),
        patch("apps.cmdb.services.node_mgmt_sync_service.CeleryUtils.create_or_update_periodic_task") as mock_create_task,
        patch("apps.cmdb.services.node_mgmt_sync_service.CeleryUtils.delete_periodic_task") as mock_delete_task,
    ):
        result = NodeMgmtSyncService.update_config(
            {
                "auto_sync_enabled": True,
                "auto_collect_enabled": False,
                "sync_interval_minutes": 15,
                "collect_interval_minutes": 20,
            }
        )

    assert result is config
    assert config.auto_sync_enabled is True
    assert config.auto_collect_enabled is False
    assert config.sync_interval_minutes == 15
    assert config.collect_interval_minutes == 20
    config.save.assert_called_once()
    mock_create_task.assert_called_once()
    create_kwargs = mock_create_task.call_args.kwargs
    assert create_kwargs["name"] == NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME
    assert create_kwargs["crontab"] == "*/15 * * * *"
    mock_delete_task.assert_called_once_with(NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME)


def test_node_mgmt_sync_service_disabling_auto_collect_deletes_node_configs():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    config = SimpleNamespace(
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=5,
        collect_interval_minutes=30,
        name="节点管理同步",
        is_builtin=True,
        save=MagicMock(),
    )
    collect_task = SimpleNamespace(id=11)

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=config),
        patch("apps.cmdb.services.node_mgmt_sync_service.transaction.atomic", return_value=_DummyAtomic()),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task]),
        patch("apps.cmdb.services.collect_service.CollectModelService.should_sync_node_params", return_value=True),
        patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params") as mock_delete,
        patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params") as mock_push,
        patch("apps.cmdb.services.node_mgmt_sync_service.CeleryUtils.create_or_update_periodic_task"),
        patch("apps.cmdb.services.node_mgmt_sync_service.CeleryUtils.delete_periodic_task"),
    ):
        NodeMgmtSyncService.update_task({"auto_collect_enabled": False})

    assert config.auto_collect_enabled is False
    mock_delete.assert_called_once_with(collect_task)
    mock_push.assert_not_called()


def test_node_mgmt_sync_service_enabling_auto_collect_pushes_node_configs():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    config = SimpleNamespace(
        auto_sync_enabled=True,
        auto_collect_enabled=False,
        sync_interval_minutes=5,
        collect_interval_minutes=30,
        name="节点管理同步",
        is_builtin=True,
        save=MagicMock(),
    )
    collect_task = SimpleNamespace(id=12)

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=config),
        patch("apps.cmdb.services.node_mgmt_sync_service.transaction.atomic", return_value=_DummyAtomic()),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task]),
        patch("apps.cmdb.services.collect_service.CollectModelService.should_sync_node_params", return_value=True),
        patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params") as mock_delete,
        patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params") as mock_push,
        patch("apps.cmdb.services.node_mgmt_sync_service.CeleryUtils.create_or_update_periodic_task"),
        patch("apps.cmdb.services.node_mgmt_sync_service.CeleryUtils.delete_periodic_task"),
    ):
        NodeMgmtSyncService.update_task({"auto_collect_enabled": True})

    assert config.auto_collect_enabled is True
    mock_delete.assert_called_once_with(collect_task)
    mock_push.assert_called_once_with(collect_task)


def test_node_mgmt_sync_service_fetch_non_container_nodes_uses_rpc_payload():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    node_mgmt = MagicMock()
    node_mgmt.cloud_region_list.return_value = [{"id": 1, "name": "default"}]
    node_mgmt.node_list.return_value = {
        "count": 1,
        "nodes": [
            {
                "id": "node-host-1",
                "ip": "10.0.0.1",
                "operating_system": "linux",
                "cloud_region": 1,
                "organization": ["1", "2"],
                "node_type": "host",
            }
        ],
    }

    with patch("apps.cmdb.services.node_mgmt_sync_service.NodeMgmt", return_value=node_mgmt):
        result = NodeMgmtSyncService._fetch_non_container_nodes()

    assert result == [
        {
            "id": "node-host-1",
            "inst_name": "10.0.0.1",
            "ip": "10.0.0.1",
            "ip_addr": "10.0.0.1",
            "cloud_region_id": 1,
            "cloud_region_name": "default",
            "cloud_name": "default",
            "operating_system": "linux",
            "os_type": "linux",
            "node_type": "host",
            "organization_ids": [1, 2],
            "organization": [1, 2],
            "model_id": "host",
            "_status": "success",
            "_error": "",
        }
    ]
    node_mgmt.node_list.assert_called_once_with({
        "page": 1,
        "page_size": NodeMgmtSyncService.NODE_MGMT_SYNC_PAGE_SIZE,
        "is_container": False,
    })


def test_node_mgmt_sync_service_pick_access_point_uses_rpc_payload():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    node_mgmt = MagicMock()
    node_mgmt.cloud_region_list.return_value = [{"id": 1, "name": "default"}]
    node_mgmt.node_list.return_value = {
        "count": 2,
        "nodes": [
            {"id": "container-old", "name": "old", "updated_at": "2025-01-01T00:00:00Z"},
            {"id": "container-new", "name": "new", "updated_at": "2025-01-02T00:00:00Z"},
        ],
    }

    with patch("apps.cmdb.services.node_mgmt_sync_service.NodeMgmt", return_value=node_mgmt):
        result = NodeMgmtSyncService._pick_access_point(1)

    assert result == {"id": "container-new", "name": "new", "cloud": 1, "cloud_name": "default"}
    node_mgmt.node_list.assert_called_once_with({
        "page": 1,
        "page_size": NodeMgmtSyncService.NODE_MGMT_SYNC_PAGE_SIZE,
        "cloud_region_id": 1,
        "is_container": True,
    })


def test_node_mgmt_sync_service_serialize_config_returns_defaults():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    config = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=5,
        collect_interval_minutes=30,
        last_sync_at=None,
        last_collect_at=None,
    )

    payload = NodeMgmtSyncService.serialize_config(config)

    assert payload == {
        "id": 1,
        "name": "节点管理同步",
        "is_builtin": True,
        "auto_sync_enabled": True,
        "auto_collect_enabled": True,
        "sync_interval_minutes": 5,
        "collect_interval_minutes": 30,
        "last_sync_at": None,
        "last_collect_at": None,
    }


def test_node_mgmt_sync_service_serialize_run_keeps_todo_for_missing_container_nodes():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    with patch.object(NodeMgmtSyncService, "get_task", return_value=SimpleNamespace(id=1)):
        run = SimpleNamespace(
            id=99,
            task_id=1,
            run_type="sync",
            status="partial_success",
            started_at=None,
            finished_at=None,
            summary_json={"all": 1},
            detail_json={"todo": [{"cloud_region_id": 1, "message": "TODO: no container node"}]},
            error_message="",
        )

        payload = NodeMgmtSyncService.serialize_run(run)

    assert payload["detail"]["todo"][0]["message"] == "TODO: no container node"
    assert payload["task_id"] == 1


def test_node_mgmt_sync_viewset_config_uses_service_result():
    from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    request.method = "GET"
    view = NodeMgmtSyncViewSet()

    with (
        patch(
            "apps.cmdb.views.node_mgmt_sync.NodeMgmtSyncService.get_task",
            return_value=SimpleNamespace(),
        ),
        patch(
            "apps.cmdb.views.node_mgmt_sync.NodeMgmtSyncService.serialize_task",
            return_value={"auto_sync_enabled": True, "id": 1},
        ) as mock_serialize,
    ):
        response = view.task(request)

    assert response.status_code == 200
    assert _response_json(response)["data"] == {"auto_sync_enabled": True, "id": 1}
    mock_serialize.assert_called_once()


def test_node_mgmt_sync_viewset_put_updates_config_via_service():
    from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    request.method = "PUT"
    request.data = {
        "auto_sync_enabled": True,
        "auto_collect_enabled": True,
        "sync_interval_minutes": 5,
        "collect_interval_minutes": 10,
    }
    view = NodeMgmtSyncViewSet()

    with (
        patch(
            "apps.cmdb.views.node_mgmt_sync.NodeMgmtSyncService.update_task",
            return_value=SimpleNamespace(),
        ) as mock_update,
        patch(
            "apps.cmdb.views.node_mgmt_sync.NodeMgmtSyncService.serialize_task",
            return_value={"auto_sync_enabled": True, "id": 1},
        ),
    ):
        response = view.task(request)

    assert response.status_code == 200
    mock_update.assert_called_once_with(request.data)


def test_node_mgmt_sync_viewset_latest_run_returns_payload():
    from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    request.GET = SimpleNamespace(get=lambda key, default=None: "sync" if key == "run_type" else default)
    view = NodeMgmtSyncViewSet()

    with patch(
        "apps.cmdb.views.node_mgmt_sync.NodeMgmtSyncService.get_latest_run_payload",
        return_value={"id": 1, "task_id": 1, "run_type": "sync"},
    ) as mock_get_payload:
        response = view.latest_run(request)

    assert response.status_code == 200
    assert _response_json(response)["data"] == {"id": 1, "task_id": 1, "run_type": "sync"}
    mock_get_payload.assert_called_once_with("sync")


def test_node_mgmt_sync_viewset_display_returns_service_payload():
    from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet

    request = _make_cmdb_request()
    request.user.permission = {"auto_collection-View"}
    view = NodeMgmtSyncViewSet()

    payload = {
        "task": {"id": 1, "name": "节点管理同步", "is_builtin": True},
        "display_source": "sync",
        "display_schema": "host_collect",
        "message": {"all": 1, "add": 0, "update": 0, "delete": 0, "association": 0},
        "summary": {"all": 1, "add": 0, "update": 0, "delete": 0, "association": 0},
        "detail": {"add": {"data": [], "count": 0}},
        "run": {"id": None, "task_id": 1, "message": {"all": 1}},
    }

    with patch("apps.cmdb.views.node_mgmt_sync.NodeMgmtSyncService.get_display_payload", return_value=payload) as mock_display:
        response = view.display(request)

    assert response.status_code == 200
    assert _response_json(response)["data"] == payload
    mock_display.assert_called_once_with()


def test_node_mgmt_sync_service_display_uses_collect_when_auto_collect_enabled():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
    )
    collect_task = SimpleNamespace(
        id=11,
        exec_status=2,
        exec_time=None,
        updated_at=None,
        created_at=None,
        collect_digest={"all": 3, "add": 1, "update": 1, "delete": 1, "association": 0},
        info={
            "add": {"data": [{"id": 1, "inst_name": "host-a", "_status": "success", "_error": ""}], "count": 1},
            "update": {"data": [], "count": 0},
            "delete": {"data": [], "count": 0},
            "relation": {"data": [], "count": 0},
            "raw_data": {"data": [], "count": 0},
        },
    )

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task]),
    ):
        payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == "collect"
    assert payload["message"]["all"] == 3
    assert payload["detail"]["add"]["data"][0]["inst_name"] == "host-a"
    assert payload["detail"]["raw_data"]["count"] == 1


def test_node_mgmt_sync_service_display_legacy_fallback_sanitizes_instance_rows():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
    )
    collect_task = SimpleNamespace(
        id=11,
        model_id="host",
        exec_status=2,
        exec_time=None,
        updated_at=None,
        created_at=None,
        collect_digest={"all": 2, "add": 0, "update": 0, "delete": 0, "association": 0},
        info={
            "add": {"data": [], "count": 0},
            "update": {"data": [], "count": 0},
            "delete": {"data": [], "count": 0},
            "relation": {"data": [], "count": 0},
            "raw_data": {"data": [], "count": 0},
        },
        instances=[
            {
                "id": "node-1",
                "inst_name": "host-a",
                "ip_addr": "10.0.0.1",
                "cloud_name": "default",
                "organization": [1],
                "password": "secret",
                "credential": {"password": "secret"},
            }
        ],
    )

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task]),
        patch.object(NodeMgmtSyncService, "get_latest_run", return_value=None),
    ):
        payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == "collect"
    assert payload["detail"]["raw_data"]["count"] == 1
    assert payload["detail"]["raw_data"]["data"][0] == {
        "id": "node-1",
        "model_id": "host",
        "inst_name": "host-a",
        "ip_addr": "10.0.0.1",
        "cloud_name": "default",
        "organization": [1],
        "_status": "success",
        "_error": "",
    }


def test_node_mgmt_sync_service_display_aggregates_collect_tasks_into_table_shape():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
    )
    collect_task_a = SimpleNamespace(
        id=11,
        exec_status=2,
        exec_time=None,
        updated_at=None,
        created_at=timezone.now(),
        collect_digest={"all": 1, "add": 1, "update": 0, "delete": 0, "association": 0},
        info={
            "add": {"data": [{"id": 1, "inst_name": "host-a", "ip_addr": "10.0.0.1"}], "count": 1},
            "update": {"data": [], "count": 0},
            "delete": {"data": [], "count": 0},
        },
    )
    collect_task_b = SimpleNamespace(
        id=12,
        exec_status=2,
        exec_time=None,
        updated_at=timezone.now(),
        created_at=timezone.now(),
        collect_digest={"all": 1, "add": 0, "update": 1, "delete": 0, "association": 1},
        info={
            "add": {"data": [], "count": 0},
            "update": {"data": [{"id": 2, "inst_name": "host-b", "ip_addr": "10.0.0.2"}], "count": 1},
            "association": {"data": [{"id": 3, "inst_name": "host-c", "ip_addr": "10.0.0.3"}], "count": 1},
        },
    )

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task_a, collect_task_b]),
        patch.object(NodeMgmtSyncService, "get_latest_run", return_value=None),
    ):
        payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == "collect"
    assert payload["message"] == {
        "all": 2,
        "add": 1,
        "update": 1,
        "delete": 0,
        "association": 1,
        "add_error": 0,
        "add_success": 1,
        "update_error": 0,
        "update_success": 1,
        "delete_error": 0,
        "delete_success": 0,
        "association_error": 0,
        "association_success": 1,
        "message": "",
    }
    assert payload["detail"]["add"]["data"][0]["inst_name"] == "host-a"
    assert payload["detail"]["update"]["data"][0]["inst_name"] == "host-b"
    assert payload["detail"]["relation"]["data"][0]["inst_name"] == "host-c"
    assert payload["detail"]["raw_data"]["count"] == 3
    assert payload["run"]["id"] == 12


def test_node_mgmt_sync_service_display_uses_collect_when_auto_collect_enabled_even_without_collect_rows():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
    )

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[]),
        patch.object(NodeMgmtSyncService, "get_latest_run", return_value=None),
    ):
        payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == "collect"
    assert payload["run"]["id"] is None
    assert payload["message"]["all"] == 0


def test_node_mgmt_sync_service_display_uses_collect_when_sync_and_collect_enabled_even_if_sync_has_data():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
    )
    sync_run = SimpleNamespace(
        id=21,
        task_id=1,
        run_type="sync",
        status="success",
        started_at=None,
        finished_at=None,
        summary_json={"all": 2, "add": 0, "update": 2, "delete": 0, "association": 0},
        detail_json={
            "add": {"data": [], "count": 0},
            "update": {"data": [{"id": "n1", "inst_name": "sync-host", "ip_addr": "10.0.0.1"}], "count": 1},
            "delete": {"data": [], "count": 0},
            "relation": {"data": [], "count": 0},
            "raw_data": {"data": [{"id": "n1", "inst_name": "sync-host", "ip_addr": "10.0.0.1"}], "count": 1},
            "todo": [],
        },
        error_message="",
    )
    collect_task = SimpleNamespace(
        id=11,
        model_id="host",
        exec_status=2,
        exec_time=None,
        updated_at=None,
        created_at=None,
        collect_digest={"all": 1, "add": 1, "update": 0, "delete": 0, "association": 0},
        info={
            "add": {"data": [{"id": 1, "inst_name": "collect-host", "ip_addr": "10.0.0.2"}], "count": 1},
            "update": {"data": [], "count": 0},
            "delete": {"data": [], "count": 0},
            "raw_data": {"data": [{"id": 1, "inst_name": "collect-host", "ip_addr": "10.0.0.2"}], "count": 1},
        },
        instances=[],
    )

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "get_latest_run", return_value=sync_run),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task]),
    ):
        payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == "collect"
    assert payload["run"]["id"] == 11
    assert payload["detail"]["add"]["data"][0]["inst_name"] == "collect-host"


def test_node_mgmt_sync_service_display_uses_collect_when_sync_and_collect_enabled():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=False,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
    )
    collect_task = SimpleNamespace(
        id=11,
        model_id="host",
        exec_status=2,
        exec_time=None,
        updated_at=None,
        created_at=None,
        collect_digest={"all": 1, "add": 0, "update": 1, "delete": 0, "association": 0},
        info={
            "add": {"data": [], "count": 0},
            "update": {"data": [{"id": 2, "inst_name": "collect-host", "ip_addr": "10.0.0.2"}], "count": 1},
            "delete": {"data": [], "count": 0},
            "raw_data": {"data": [{"id": 2, "inst_name": "collect-host", "ip_addr": "10.0.0.2"}], "count": 1},
        },
        instances=[],
    )

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task]),
    ):
        payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == "collect"
    assert payload["run"]["id"] == 11
    assert payload["detail"]["update"]["data"][0]["inst_name"] == "collect-host"


def test_node_mgmt_sync_service_display_uses_sync_when_both_switches_disabled():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=False,
        auto_collect_enabled=False,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
    )
    sync_run = SimpleNamespace(
        id=31,
        task_id=1,
        run_type="sync",
        status="success",
        started_at=None,
        finished_at=None,
        summary_json={"all": 1, "add": 1, "update": 0, "delete": 0, "association": 0},
        detail_json={
            "add": {"data": [{"id": "n1", "inst_name": "sync-host", "ip_addr": "10.0.0.1"}], "count": 1},
            "update": {"data": [], "count": 0},
            "delete": {"data": [], "count": 0},
            "relation": {"data": [], "count": 0},
            "raw_data": {"data": [{"id": "n1", "inst_name": "sync-host", "ip_addr": "10.0.0.1"}], "count": 1},
            "todo": [],
        },
        error_message="",
    )

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "get_latest_run", return_value=sync_run),
    ):
        payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == "sync"
    assert payload["run"]["id"] == 31
    assert payload["detail"]["add"]["data"][0]["inst_name"] == "sync-host"


def test_base_collect_format_collect_data_derives_raw_data_from_diff_buckets():
    from apps.cmdb.collection.collect_tasks.base import BaseCollect

    collector = BaseCollect.__new__(BaseCollect)
    result = {
        "host": {
            "add": {
                "success": [
                    {
                        "inst_info": {
                            "model_id": "host",
                            "inst_name": "host-a",
                            "ip_addr": "10.0.0.1",
                            "_id": 1,
                        }
                    }
                ],
                "failed": [],
            },
            "update": {
                "success": [
                    {
                        "inst_info": {
                            "model_id": "host",
                            "inst_name": "host-b",
                            "ip_addr": "10.0.0.2",
                            "_id": 2,
                        }
                    }
                ],
                "failed": [],
            },
            "delete": {"success": [], "failed": []},
        },
        "all": 2,
    }

    format_data = collector.format_collect_data(result)

    assert format_data["all"] == 2
    assert len(format_data["__raw_data__"]) == 2
    assert [item["inst_name"] for item in format_data["__raw_data__"]] == ["host-a", "host-b"]
    assert [item["_status"] for item in format_data["__raw_data__"]] == ["success", "success"]


def test_base_collect_format_collect_data_sanitizes_derived_raw_data():
    from apps.cmdb.collection.collect_tasks.base import BaseCollect

    collector = BaseCollect.__new__(BaseCollect)
    result = {
        "host": {
            "add": {
                "success": [
                    {
                        "inst_info": {
                            "model_id": "host",
                            "inst_name": "host-a",
                            "ip_addr": "10.0.0.1",
                            "_id": 1,
                            "password": "secret",
                            "credential": {"token": "secret"},
                        }
                    }
                ],
                "failed": [],
            },
            "update": {"success": [], "failed": []},
            "delete": {"success": [], "failed": []},
        },
        "all": 1,
    }

    format_data = collector.format_collect_data(result)

    assert format_data["__raw_data__"] == [
        {
            "_id": 1,
            "model_id": "host",
            "inst_name": "host-a",
            "ip_addr": "10.0.0.1",
            "_status": "success",
        }
    ]


def test_node_mgmt_sync_service_sync_hosts_creates_run_with_task():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
        save=MagicMock(),
    )
    sync_run = SimpleNamespace(
        id=7,
        task_id=1,
        run_type="sync",
        status="running",
        started_at=None,
        finished_at=None,
        summary_json={},
        detail_json={},
        error_message="",
        save=MagicMock(),
    )
    hidden_task = SimpleNamespace(id=9, save=MagicMock())
    graph_instance = {
        "_id": 101,
        "id": "node-host-1",
        "model_id": "host",
        "inst_name": "10.0.0.1[default]",
        "ip_addr": "10.0.0.1",
        "cloud": 1,
        "cloud_id": 1,
        "cloud_name": "default",
    }
    nodes = [
        {
            "id": "node-host-1",
            "ip": "10.0.0.1",
            "ip_addr": "10.0.0.1",
            "cloud_region_id": 1,
            "cloud_region_name": "default",
            "operating_system": "linux",
            "node_type": "host",
            "organization_ids": [1],
            "inst_name": "host-1",
        }
    ]

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=task),
        patch.object(NodeMgmtSyncService, "_fetch_non_container_nodes", return_value=nodes),
        patch.object(NodeMgmtSyncService, "_group_nodes_by_region", return_value={1: nodes}),
        patch.object(NodeMgmtSyncService, "_pick_access_point", return_value=None),
        patch.object(NodeMgmtSyncService, "_ensure_region_collect_task", return_value=hidden_task) as mock_ensure_task,
        patch.object(NodeMgmtSyncService, "_load_existing_host_map", return_value={}),
        patch.object(NodeMgmtSyncService, "_query_region_host_instances", return_value=[graph_instance]),
        patch.object(NodeMgmtSyncService, "_build_sync_run", return_value=sync_run) as mock_build_run,
        patch("apps.cmdb.services.node_mgmt_sync_service.InstanceManage.instance_create", return_value=graph_instance) as mock_create_instance,
    ):
        payload = NodeMgmtSyncService.sync_hosts()

    mock_build_run.assert_called_once_with(task=task)
    mock_create_instance.assert_called_once()
    assert mock_ensure_task.call_args.kwargs["instances"] == [graph_instance]
    assert payload["task_id"] == 1


def test_node_mgmt_sync_service_collect_task_payload_does_not_inline_scan_cycle():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    payload = NodeMgmtSyncService._collect_task_payload(
        cloud_region_id=1,
        cloud_region_name="default",
        access_point=None,
        team=[1],
        instances=[],
        interval_minutes=10,
    )

    assert "scan_cycle" not in payload


def test_node_mgmt_sync_service_ensure_region_collect_task_sets_schedule_fields_on_create():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=SimpleNamespace(auto_collect_enabled=True)),
        patch("apps.cmdb.services.node_mgmt_sync_service.CollectModels.objects.filter") as mock_filter,
        patch("apps.cmdb.services.node_mgmt_sync_service.CollectModels.objects.create") as mock_create,
        patch("apps.cmdb.services.collect_service.CollectModelService.should_sync_node_params", return_value=True),
        patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params") as mock_push,
    ):
        mock_filter.return_value.first.return_value = None
        mock_create.return_value = SimpleNamespace(id=1)

        NodeMgmtSyncService._ensure_region_collect_task(
            cloud_region_id=1,
            cloud_region_name="default",
            access_point=None,
            team=[1],
            instances=[],
            interval_minutes=10,
        )

    create_kwargs = mock_create.call_args.kwargs
    assert create_kwargs["is_interval"] is True
    assert create_kwargs["cycle_value_type"] == "cycle"
    assert create_kwargs["cycle_value"] == "10"
    assert create_kwargs["scan_cycle"] == "*/10 * * * *"
    mock_push.assert_called_once_with(mock_create.return_value)


def test_node_mgmt_sync_service_ensure_region_collect_task_sets_schedule_fields_on_update():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        instances=[],
        access_point=[],
        save=MagicMock(),
    )
    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=SimpleNamespace(auto_collect_enabled=True)),
        patch("apps.cmdb.services.node_mgmt_sync_service.CollectModels.objects.filter") as mock_filter,
        patch("apps.cmdb.services.collect_service.CollectModelService.should_sync_node_params", return_value=True),
        patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params") as mock_delete,
        patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params") as mock_push,
    ):
        mock_filter.return_value.first.return_value = task

        NodeMgmtSyncService._ensure_region_collect_task(
            cloud_region_id=1,
            cloud_region_name="default",
            access_point=None,
            team=[1],
            instances=[],
            interval_minutes=10,
        )

    assert task.is_interval is True
    assert task.cycle_value_type == "cycle"
    assert task.cycle_value == "10"
    assert task.scan_cycle == "*/10 * * * *"
    task.save.assert_called_once_with()
    mock_delete.assert_not_called()
    mock_push.assert_not_called()


def test_node_mgmt_sync_service_ensure_region_collect_task_repushes_when_instances_changed():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        instances=[{"id": "node-1", "ip_addr": "10.0.0.1", "inst_name": "10.0.0.1[default]"}],
        access_point=[],
        save=MagicMock(),
    )
    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=SimpleNamespace(auto_collect_enabled=True)),
        patch("apps.cmdb.services.node_mgmt_sync_service.CollectModels.objects.filter") as mock_filter,
        patch("apps.cmdb.services.collect_service.CollectModelService.should_sync_node_params", return_value=True),
        patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params") as mock_delete,
        patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params") as mock_push,
    ):
        mock_filter.return_value.first.return_value = task

        NodeMgmtSyncService._ensure_region_collect_task(
            cloud_region_id=1,
            cloud_region_name="default",
            access_point=None,
            team=[1],
            instances=[{"id": "node-2", "ip_addr": "10.0.0.2", "inst_name": "10.0.0.2[default]"}],
            interval_minutes=10,
        )

    mock_delete.assert_called_once()
    mock_push.assert_called_once_with(task)


def test_node_mgmt_sync_service_ensure_region_collect_task_repushes_when_access_point_changed():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    task = SimpleNamespace(
        instances=[{"id": "node-1", "ip_addr": "10.0.0.1", "inst_name": "10.0.0.1[default]"}],
        access_point=[{"id": "container-old", "cloud": 1, "cloud_name": "default"}],
        save=MagicMock(),
    )
    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=SimpleNamespace(auto_collect_enabled=True)),
        patch("apps.cmdb.services.node_mgmt_sync_service.CollectModels.objects.filter") as mock_filter,
        patch("apps.cmdb.services.collect_service.CollectModelService.should_sync_node_params", return_value=True),
        patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params") as mock_delete,
        patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params") as mock_push,
    ):
        mock_filter.return_value.first.return_value = task

        NodeMgmtSyncService._ensure_region_collect_task(
            cloud_region_id=1,
            cloud_region_name="default",
            access_point={"id": "container-new", "cloud": 1, "cloud_name": "default"},
            team=[1],
            instances=[{"id": "node-1", "ip_addr": "10.0.0.1", "inst_name": "10.0.0.1[default]"}],
            interval_minutes=10,
        )

    mock_delete.assert_called_once()
    mock_push.assert_called_once_with(task)


def test_node_mgmt_sync_service_ensure_region_collect_task_does_not_push_when_auto_collect_disabled():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    with (
        patch.object(NodeMgmtSyncService, "get_task", return_value=SimpleNamespace(auto_collect_enabled=False)),
        patch("apps.cmdb.services.node_mgmt_sync_service.CollectModels.objects.filter") as mock_filter,
        patch("apps.cmdb.services.node_mgmt_sync_service.CollectModels.objects.create") as mock_create,
        patch("apps.cmdb.services.collect_service.CollectModelService.should_sync_node_params", return_value=True),
        patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params") as mock_delete,
        patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params") as mock_push,
    ):
        mock_filter.return_value.first.return_value = None
        mock_create.return_value = SimpleNamespace(id=1)

        NodeMgmtSyncService._ensure_region_collect_task(
            cloud_region_id=1,
            cloud_region_name="default",
            access_point=None,
            team=[1],
            instances=[],
            interval_minutes=10,
        )

    mock_delete.assert_not_called()
    mock_push.assert_not_called()


def test_vmware_node_params_uses_30_minute_interval():
    from apps.cmdb.node_configs.cloud.vmware import VmwareNodeParams

    assert VmwareNodeParams.interval == 30 * 60


def test_node_mgmt_sync_service_maps_host_os_type_from_model_options():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    host_model = {
        "attrs": [
            {
                "attr_id": "os_type",
                "attr_type": "enum",
                "option": [
                    {"id": "1", "name": "Linux"},
                    {"id": "2", "name": "Windows"},
                    {"id": "3", "name": "AIX"},
                    {"id": "4", "name": "Unix"},
                    {"id": "other", "name": "Other"},
                ],
            }
        ]
    }

    with patch("apps.cmdb.services.node_mgmt_sync_service.ModelManage.search_model_info", return_value=host_model):
        payload = NodeMgmtSyncService._build_host_instance_payload(
            node={
                "id": "node-1",
                "cloud_region_id": 1,
                "cloud_region_name": "default",
                "ip": "10.0.0.1",
                "operating_system": "linux",
                "organization_ids": [1],
            },
            collect_task_id=9,
        )

    assert payload["os_type"] == "1"
    assert payload["inst_name"] == "10.0.0.1[default]"


def test_node_mgmt_sync_service_maps_unknown_host_os_type_to_other():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    host_model = {
        "attrs": [
            {
                "attr_id": "os_type",
                "attr_type": "enum",
                "option": [
                    {"id": "1", "name": "Linux"},
                    {"id": "2", "name": "Windows"},
                    {"id": "other", "name": "Other"},
                ],
            }
        ]
    }

    with patch("apps.cmdb.services.node_mgmt_sync_service.ModelManage.search_model_info", return_value=host_model):
        payload = NodeMgmtSyncService._build_host_instance_payload(
            node={
                "id": "node-2",
                "cloud_region_id": 1,
                "cloud_region_name": "default",
                "ip": "10.0.0.2",
                "operating_system": "solaris",
                "organization_ids": [1],
            },
            collect_task_id=9,
        )

    assert payload["os_type"] == "other"


def test_node_mgmt_sync_service_sync_hosts_marks_missing_container_node_as_todo():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    config = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
        save=MagicMock(),
    )
    sync_run = SimpleNamespace(
        id=7,
        task_id=1,
        run_type="sync",
        status="running",
        started_at=None,
        finished_at=None,
        summary_json={},
        detail_json={},
        error_message="",
        save=MagicMock(),
    )
    hidden_task = SimpleNamespace(id=9)
    host_model = {"attrs": []}

    nodes = [
        {
            "id": "node-host-1",
            "ip": "10.0.0.1",
            "cloud_region_id": 1,
            "cloud_region_name": "default",
            "operating_system": "linux",
            "node_type": "host",
            "organization_ids": [1],
        }
    ]

    with (
        patch.object(NodeMgmtSyncService, "get_config", return_value=config),
        patch.object(NodeMgmtSyncService, "get_task", return_value=config),
        patch.object(NodeMgmtSyncService, "_fetch_non_container_nodes", return_value=nodes),
        patch.object(NodeMgmtSyncService, "_group_nodes_by_region", return_value={1: nodes}),
        patch.object(NodeMgmtSyncService, "_pick_access_point", return_value=None),
        patch.object(NodeMgmtSyncService, "_ensure_region_collect_task", return_value=hidden_task),
        patch.object(NodeMgmtSyncService, "_load_existing_host_map", return_value={}),
        patch.object(NodeMgmtSyncService, "_build_sync_run", return_value=sync_run),
        patch("apps.cmdb.services.node_mgmt_sync_service.ModelManage.search_model_info", return_value=host_model),
        patch("apps.cmdb.services.node_mgmt_sync_service.InstanceManage.instance_create") as mock_create_instance,
    ):
        payload = NodeMgmtSyncService.sync_hosts()

    mock_create_instance.assert_called_once()
    assert payload["message"]["add"] == 1
    assert payload["detail"]["raw_data"]["count"] == 1
    assert payload["detail"]["todo"][0]["message"].startswith("TODO: region 1")


def test_node_mgmt_sync_service_collect_hosts_skips_regions_without_access_point():
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    config = SimpleNamespace(
        id=1,
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
        sync_interval_minutes=10,
        collect_interval_minutes=10,
        last_sync_at=None,
        last_collect_at=None,
        save=MagicMock(),
    )
    collect_run = SimpleNamespace(
        id=8,
        task_id=1,
        run_type="collect",
        status="running",
        started_at=None,
        finished_at=None,
        summary_json={},
        detail_json={},
        error_message="",
        save=MagicMock(),
    )
    hidden_task = SimpleNamespace(id=11, name="region-task", access_point=[])

    with (
        patch.object(NodeMgmtSyncService, "get_config", return_value=config),
        patch.object(NodeMgmtSyncService, "get_task", return_value=config),
        patch.object(NodeMgmtSyncService, "_build_collect_run", return_value=collect_run),
        patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[hidden_task]),
        patch.object(NodeMgmtSyncService, "_execute_collect_task") as mock_exec_task,
    ):
        payload = NodeMgmtSyncService.collect_hosts()

    mock_exec_task.assert_not_called()
    assert payload["detail"]["todo"][0]["task_id"] == 11


def test_instance_association_instance_list_allows_user_with_object_permission():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    instance = _make_instance()
    associations = [{"_id": 1, "inst_name": "related-host"}]

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=instance,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
            return_value=True,
        ) as mock_check_permission,
        patch(
            "apps.cmdb.views.instance.InstanceManage.instance_association_instance_list",
            return_value=associations,
        ) as mock_association_list,
    ):
        response = InstanceViewSet().instance_association_instance_list(
            request,
            "host",
            1001,
        )

    assert response.status_code == 200
    assert _response_json(response)["data"] == associations
    mock_check_permission.assert_called_once_with(request, instance, VIEW)
    mock_association_list.assert_called_once_with("host", 1001)


def test_instance_association_instance_list_allows_creator_with_org_access():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    instance = _make_instance(creator="alice")
    associations = [{"_id": 2, "inst_name": "creator-related-host"}]

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=instance,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
        ) as mock_check_permission,
        patch(
            "apps.cmdb.views.instance.InstanceManage.instance_association_instance_list",
            return_value=associations,
        ) as mock_association_list,
    ):
        response = InstanceViewSet().instance_association_instance_list(
            request,
            "host",
            1001,
        )

    assert response.status_code == 200
    assert _response_json(response)["data"] == associations
    mock_check_permission.assert_not_called()
    mock_association_list.assert_called_once_with("host", 1001)


def test_instance_association_instance_list_returns_404_when_instance_missing():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=None,
        ),
        patch("apps.cmdb.views.instance.InstanceManage.instance_association_instance_list") as mock_association_list,
    ):
        response = InstanceViewSet().instance_association_instance_list(
            request,
            "host",
            1001,
        )

    assert response.status_code == 404
    assert _response_json(response)["result"] is False
    mock_association_list.assert_not_called()


def test_instance_association_denies_user_without_object_permission():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    instance = _make_instance()

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=instance,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
            return_value=False,
        ) as mock_check_permission,
        patch("apps.cmdb.views.instance.InstanceManage.instance_association") as mock_association,
    ):
        response = InstanceViewSet().instance_association(request, "host", 1001)

    assert response.status_code == 403
    assert _response_json(response)["result"] is False
    mock_check_permission.assert_called_once_with(request, instance, VIEW)
    mock_association.assert_not_called()


def test_instance_association_allows_creator_with_org_access():
    from apps.cmdb.views.instance import InstanceViewSet

    request = _make_cmdb_request(username="alice")
    instance = _make_instance(creator="alice")
    associations = [{"_id": 3, "inst_name": "related-app"}]

    with (
        patch(
            "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
            return_value=instance,
        ),
        patch.object(
            InstanceViewSet,
            "check_instance_permission",
        ) as mock_check_permission,
        patch(
            "apps.cmdb.views.instance.InstanceManage.instance_association",
            return_value=associations,
        ) as mock_association,
    ):
        response = InstanceViewSet().instance_association(request, "host", 1001)

    assert response.status_code == 200
    assert _response_json(response)["data"] == associations
    mock_check_permission.assert_not_called()
    mock_association.assert_called_once_with("host", 1001)


class CQLQueryTest:
    """
    用于测试和执行CQL查询的辅助类

    使用示例:
        test = CQLQueryTest()

        # 查询所有节点
        result = test.query("MATCH (n) RETURN n LIMIT 10")

        # 查询特定标签的节点
        result = test.query("MATCH (n:主机) RETURN n LIMIT 5")

        # 查询节点和关系
        result = test.query("MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 10")
    """

    def __init__(self):
        """初始化GraphClient连接"""
        self.client = None

    def query(self, cql: str, format_result: bool = True):
        """
        执行CQL查询

        Args:
            cql: CQL查询语句
            format_result: 是否格式化返回结果,默认True

        Returns:
            查询结果列表或原始结果
        """
        try:
            with GraphClient() as client:
                logger.info(f"执行CQL查询: {cql}")
                result = client._execute_query(cql)

                if format_result:
                    # 格式化结果为字典列表
                    formatted = client.entity_to_list(result)
                    logger.info(f"查询成功,返回{len(formatted)}条记录")
                    return formatted
                else:
                    logger.info("查询成功,返回原始结果")
                    return result

        except Exception as e:
            logger.error(f"CQL查询执行失败: {str(e)}")
            raise

    def query_nodes(self, label: str = "", limit: int = 10, conditions: str = ""):
        """
        便捷方法:查询节点

        Args:
            label: 节点标签,如"主机"、"应用"等,为空则查询所有节点
            limit: 返回结果数量限制
            conditions: WHERE条件,如"n.name = '测试主机'"

        Returns:
            节点列表
        """
        label_str = f":{label}" if label else ""
        where_str = f"WHERE {conditions}" if conditions else ""

        cql = f"MATCH (n{label_str}) {where_str} RETURN n LIMIT {limit}"
        return self.query(cql)

    def query_relationships(self, src_label: str = "", rel_type: str = "", dst_label: str = "", limit: int = 10):
        """
        便捷方法:查询关系

        Args:
            src_label: 源节点标签
            rel_type: 关系类型
            dst_label: 目标节点标签
            limit: 返回结果数量限制

        Returns:
            关系列表(包含源节点、关系、目标节点)
        """
        src_str = f":{src_label}" if src_label else ""
        rel_str = f":{rel_type}" if rel_type else ""
        dst_str = f":{dst_label}" if dst_label else ""

        cql = f"MATCH (n{src_str})-[r{rel_str}]->(m{dst_str}) RETURN n, r, m LIMIT {limit}"
        return self.query(cql)

    def count_nodes(self, label: str = "", conditions: str = ""):
        """
        便捷方法:统计节点数量

        Args:
            label: 节点标签
            conditions: WHERE条件

        Returns:
            节点数量
        """
        label_str = f":{label}" if label else ""
        where_str = f"WHERE {conditions}" if conditions else ""

        cql = f"MATCH (n{label_str}) {where_str} RETURN count(n) as count"
        result = self.query(cql, format_result=False)

        # 从结果中提取count值
        if result and len(result.result_set) > 0:
            return result.result_set[0][0]
        return 0

    def get_node_by_id(self, node_id: int):
        """
        便捷方法:根据ID查询节点

        Args:
            node_id: 节点ID

        Returns:
            节点信息字典
        """
        cql = f"MATCH (n) WHERE ID(n) = {node_id} RETURN n"
        result = self.query(cql)
        return result[0] if result else None


if __name__ == "__main__":
    query = "MATCH (n:k8s_test)  RETURN n ORDER BY ID(n) ASC"
    tester = CQLQueryTest()
    res = tester.query(query)
    for item in res:
        print(item)


class CollectToolPermissionTests(SimpleTestCase):
    def _make_request(self, username="tester", domain="default"):
        return SimpleNamespace(
            user=SimpleNamespace(username=username, domain=domain),
            COOKIES={"current_team": "1", "include_children": "0"},
        )

    def test_debug_state_access_isolated_by_owner(self):
        request = self._make_request(username="alice")
        owner = {"username": "alice", "domain": "default"}
        other_owner = {"username": "bob", "domain": "default"}

        self.assertTrue(CollectToolService.can_access_debug_state({"owner": owner}, request))
        self.assertFalse(CollectToolService.can_access_debug_state({"owner": other_owner}, request))

    def test_save_debug_state_preserves_owner_between_status_updates(self):
        debug_id = "dbg_test_owner"
        owner = {"username": "alice", "domain": "default"}

        cache_store = {}

        def fake_get(key):
            return cache_store.get(key)

        def fake_set(key, value, timeout=None):
            cache_store[key] = value

        with (
            patch("apps.cmdb.services.collect_tool_service.cache.get", side_effect=fake_get),
            patch("apps.cmdb.services.collect_tool_service.cache.set", side_effect=fake_set),
        ):
            CollectToolService.save_debug_state(debug_id, "pending", owner=owner)
            CollectToolService.save_debug_state(debug_id, "running")
            state = CollectToolService.get_debug_state(debug_id)

        self.assertEqual(state["owner"], owner)
        self.assertEqual(state["status"], "running")

    def test_build_debug_owner_uses_request_identity(self):
        request = self._make_request(username="alice", domain="default")

        owner = CollectToolService.build_debug_owner(request)

        self.assertEqual(owner["username"], "alice")
        self.assertEqual(owner["domain"], "default")

    def test_get_accessible_task_denies_without_object_permission(self):
        request = self._make_request(username="alice")
        fake_task = SimpleNamespace(id=123, task_type="protocol")

        with (
            patch(
                "apps.cmdb.services.collect_tool_service.CollectModels.objects.get",
                return_value=fake_task,
            ),
            patch(
                "apps.cmdb.permissions.inst_task_permission.InstanceTaskPermission.has_object_permission",
                return_value=False,
            ),
        ):
            with self.assertRaises(ValidationError):
                CollectToolService.get_accessible_task(request, 123, operator="View")

    def test_inject_credentials_replaces_masked_password_from_accessible_task(self):
        payload = {
            "protocol": "ipmi",
            "credential": {"username": "admin", "password": "••••••"},
        }
        fake_task = SimpleNamespace(decrypt_credentials={"password": "real-secret"})

        result = CollectToolService.inject_credentials(payload, fake_task)

        self.assertEqual(result["credential"]["password"], "real-secret")

    def test_resolve_access_point_denies_without_node_permission(self):
        request = self._make_request(username="alice")

        with patch(
            "apps.rpc.node_mgmt.NodeMgmt.get_authorized_nodes_by_ids",
            return_value=[],
        ):
            with self.assertRaises(ValidationError):
                CollectToolService.resolve_access_point(request, "node-1")

    def test_execute_debug_maps_error_field_to_summary_and_raw_log(self):
        payload = {
            "protocol": "snmp",
            "action": "raw_collect",
            "target": "10.0.0.1",
            "port": 161,
            "credential": {"version": "v2c", "community": "public"},
        }

        with patch("apps.cmdb.services.collect_tool_service.Stargazer") as mock_stargazer_cls:
            mock_stargazer_cls.return_value.collection_tool_debug.return_value = {
                "success": False,
                "error": "maximum payload exceeded",
            }

            result = CollectToolService.execute_debug(
                payload=payload,
                service_name="default_stargazer",
                timeout=30,
                request_id="dbg_test_error",
            )

        self.assertEqual(result["summary"], "maximum payload exceeded")
        self.assertEqual(result["raw_log"], "maximum payload exceeded")
        self.assertEqual(result["stage"], "unknown")


class CmdbPermissionScopeRegressionTests(SimpleTestCase):
    def _make_request(self, current_team="1", include_children="1", group_list=None, is_superuser=False):
        return SimpleNamespace(
            user=SimpleNamespace(
                username="alice",
                domain="default",
                group_list=group_list or [{"id": 1}, {"id": 2}],
                group_tree=[],
                is_superuser=is_superuser,
            ),
            COOKIES={"current_team": current_team, "include_children": include_children},
        )

    def test_format_user_groups_permissions_uses_authorized_children_only(self):
        request = self._make_request()
        permission_rules = {"team": [1], "instance": []}

        with (
            patch(
                "apps.cmdb.utils.permission_util.CmdbRulesFormatUtil.get_authorized_team_ids",
                return_value=[1, 2],
            ),
            patch(
                "apps.cmdb.utils.permission_util.get_permission_rules",
                return_value=permission_rules,
            ),
        ):
            permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(
                request,
                model_id="host",
                permission_type=PERMISSION_INSTANCES,
            )

        self.assertEqual(permission_map[1]["inst_names"], [])
        deny_inst_name = permission_map[2]["inst_names"][0]
        self.assertTrue(deny_inst_name.startswith(f"{DENY_PERMISSION_PLACEHOLDER}:"))
        self.assertEqual(permission_map[2]["permission_instances_map"], {deny_inst_name: []})

    def test_format_user_groups_permissions_preserves_instance_level_permissions(self):
        request = self._make_request()
        permission_rules = {
            "team": [],
            "instance": [{"id": "host-a", "permission": [VIEW]}],
        }

        with (
            patch(
                "apps.cmdb.utils.permission_util.CmdbRulesFormatUtil.get_authorized_team_ids",
                return_value=[2],
            ),
            patch(
                "apps.cmdb.utils.permission_util.get_permission_rules",
                return_value=permission_rules,
            ),
        ):
            permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(
                request,
                model_id="host",
                permission_type=PERMISSION_INSTANCES,
            )

        self.assertEqual(permission_map[2]["inst_names"], ["host-a"])
        self.assertEqual(permission_map[2]["permission_instances_map"], {"host-a": [VIEW]})

    def test_format_user_groups_permissions_falls_back_to_deny_placeholder_when_no_authorized_team(self):
        request = self._make_request(current_team="9", group_list=[{"id": 1}])

        with (
            patch(
                "apps.cmdb.utils.permission_util.CmdbRulesFormatUtil.get_authorized_team_ids",
                return_value=[],
            ),
            patch(
                "apps.cmdb.utils.permission_util.get_permission_rules",
                return_value={},
            ),
        ):
            permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(
                request,
                model_id="host",
                permission_type=PERMISSION_INSTANCES,
            )

        deny_inst_name = permission_map[9]["inst_names"][0]
        self.assertTrue(deny_inst_name.startswith(f"{DENY_PERMISSION_PLACEHOLDER}:"))
        self.assertEqual(permission_map, {9: {"permission_instances_map": {deny_inst_name: []}, "inst_names": [deny_inst_name]}})

    def test_build_permission_params_keeps_single_org_boundary_for_instance_permissions(self):
        permission_map = {2: {"permission_instances_map": {"host-a": [VIEW]}, "inst_names": ["host-a"]}}

        with patch.object(GraphClient, "_get_driver_type", return_value=GraphClient.DRIVER_FALKORDB):
            permission_params, permission_params_dict = InstanceManage._build_permission_params(permission_map, creator="alice")

        self.assertIn("n.organization", permission_params)
        self.assertIn(" AND ", permission_params)
        self.assertIn("n.inst_name", permission_params)
        self.assertIn("n._creator", permission_params)
        self.assertGreaterEqual(len(permission_params_dict), 3)

    def test_build_permission_params_ors_across_orgs_but_keeps_branch_boundaries(self):
        deny_inst_name = f"{DENY_PERMISSION_PLACEHOLDER}:placeholder"
        permission_map = {
            1: {"permission_instances_map": {}, "inst_names": []},
            2: {"permission_instances_map": {deny_inst_name: []}, "inst_names": [deny_inst_name]},
        }

        with patch.object(GraphClient, "_get_driver_type", return_value=GraphClient.DRIVER_FALKORDB):
            permission_params, permission_params_dict = InstanceManage._build_permission_params(permission_map, creator="alice")

        self.assertIn(" OR ", permission_params)
        self.assertIn(" AND ", permission_params)
        self.assertIn("n.organization", permission_params)
        self.assertGreaterEqual(len(permission_params_dict), 4)

    @staticmethod
    def _build_graph_client_context_with_driver_methods(method_name, return_value):
        with patch.object(GraphClient, "_get_driver_type", return_value=GraphClient.DRIVER_FALKORDB):
            graph_client = GraphClient()
        driver = graph_client._client
        setattr(driver, method_name, MagicMock(return_value=return_value))
        graph_client.__enter__()
        return graph_client, getattr(driver, method_name)

    def test_fulltext_search_passes_branch_scoped_permission_params_to_driver(self):
        permission_map = {2: {"permission_instances_map": {"host-a": [VIEW]}, "inst_names": ["host-a"]}}
        graph_client, full_text_mock = self._build_graph_client_context_with_driver_methods("full_text", [])

        with (
            patch.object(GraphClient, "_get_driver_type", return_value=GraphClient.DRIVER_FALKORDB),
            patch("apps.cmdb.services.instance.GraphClient", return_value=graph_client),
        ):
            InstanceManage.fulltext_search(search="host-a", permission_map=permission_map, creator="alice")

        full_text_mock.assert_called_once()
        kwargs = full_text_mock.call_args.kwargs
        self.assertIn("n.organization", kwargs["permission_params"])
        self.assertIn(" AND ", kwargs["permission_params"])
        self.assertEqual(kwargs["inst_name_params"], "")
        self.assertEqual(kwargs["created"], "")

    def test_fulltext_search_stats_passes_deny_placeholder_inside_org_branch(self):
        deny_inst_name = f"{DENY_PERMISSION_PLACEHOLDER}:placeholder"
        permission_map = {
            1: {"permission_instances_map": {}, "inst_names": []},
            2: {"permission_instances_map": {deny_inst_name: []}, "inst_names": [deny_inst_name]},
        }
        graph_client, full_text_stats_mock = self._build_graph_client_context_with_driver_methods(
            "full_text_stats", {"total": 0, "model_stats": []}
        )

        with (
            patch.object(GraphClient, "_get_driver_type", return_value=GraphClient.DRIVER_FALKORDB),
            patch("apps.cmdb.services.instance.GraphClient", return_value=graph_client),
        ):
            InstanceManage.fulltext_search_stats(search="host-a", permission_map=permission_map, creator="alice")

        kwargs = full_text_stats_mock.call_args.kwargs
        self.assertIn("placeholder", kwargs["permission_params"])
        self.assertIn(" AND ", kwargs["permission_params"])
        self.assertIn(" OR ", kwargs["permission_params"])
        self.assertIsInstance(kwargs["permission_params_dict"], dict)

    def test_fulltext_search_by_model_uses_same_branch_scoped_permission_params(self):
        permission_map = {2: {"permission_instances_map": {"host-a": [VIEW]}, "inst_names": ["host-a"]}}
        graph_client, full_text_by_model_mock = self._build_graph_client_context_with_driver_methods(
            "full_text_by_model", {"model_id": "host", "total": 0, "page": 1, "page_size": 10, "data": []}
        )

        with (
            patch.object(GraphClient, "_get_driver_type", return_value=GraphClient.DRIVER_FALKORDB),
            patch("apps.cmdb.services.instance.GraphClient", return_value=graph_client),
        ):
            InstanceManage.fulltext_search_by_model(
                search="host-a",
                model_id="host",
                permission_map=permission_map,
                creator="alice",
                page=1,
                page_size=10,
            )

        kwargs = full_text_by_model_mock.call_args.kwargs
        self.assertIn("n.organization", kwargs["permission_params"])
        self.assertIn(" AND ", kwargs["permission_params"])
        self.assertEqual(kwargs["created"], "")

    def test_build_permission_map_reuses_safe_permission_rule_builder(self):
        from apps.opspilot.metis.llm.tools.cmdb.utils import build_permission_map

        user = SimpleNamespace(group_list=[{"id": 1}, {"id": 2}])
        permission_rules = {"team": [1], "instance": []}

        with (
            patch(
                "apps.opspilot.metis.llm.tools.cmdb.utils.get_permission_rules",
                return_value=permission_rules,
            ),
            patch(
                "apps.opspilot.metis.llm.tools.cmdb.utils.CmdbRulesFormatUtil.build_permission_rule_map",
                return_value={2: {"permission_instances_map": {DENY_PERMISSION_PLACEHOLDER: []}, "inst_names": [DENY_PERMISSION_PLACEHOLDER]}},
            ) as mock_build,
        ):
            result = build_permission_map(
                user=user,
                current_team=1,
                include_children=True,
                permission_type=PERMISSION_INSTANCES,
                model_id="host",
            )

        mock_build.assert_called_once()
        self.assertEqual(result[2]["inst_names"], [DENY_PERMISSION_PLACEHOLDER])

    def test_nats_permission_map_uses_safe_permission_rule_builder(self):
        from apps.cmdb.nats.nats import _build_nats_permission_map

        user_info = {"team": 1, "user": "alice", "domain": "default", "include_children": True}
        real_user = SimpleNamespace(username="alice", domain="default", group_list=[{"id": 1}, {"id": 2}])

        with (
            patch("apps.cmdb.nats.nats.User.objects.filter") as mock_filter,
            patch("apps.cmdb.nats.nats._get_authorized_team_ids", return_value=[1, 2]),
            patch("apps.cmdb.nats.nats.get_permission_rules", return_value={"team": [1], "instance": []}),
            patch(
                "apps.cmdb.nats.nats.CmdbRulesFormatUtil.build_permission_rule_map",
                return_value={2: {"permission_instances_map": {DENY_PERMISSION_PLACEHOLDER: []}, "inst_names": [DENY_PERMISSION_PLACEHOLDER]}},
            ) as mock_build,
        ):
            mock_filter.return_value.first.return_value = real_user
            result = _build_nats_permission_map(user_info)

        mock_build.assert_called_once_with(user_teams=[1, 2], permission_rules={"team": [1], "instance": []}, fallback_team_id=1)
        self.assertEqual(result[2]["inst_names"], [DENY_PERMISSION_PLACEHOLDER])
def test_config_file_collect_triggers_stargazer_and_returns_pending_result():
    from apps.cmdb.collection.collect_tasks.config_file_collect import ConfigFileCollect

    task = SimpleNamespace(
        id=267,
        params={"config_file_path": "/opt/bk-lite/common.env"},
        instances=[{"inst_name": "10.0.0.1[default]"}],
        timeout=30,
    )
    node_params = MagicMock()
    node_params.custom_headers.return_value = {
        "cmdbplugin_name": "config_file_info",
        "cmdbhosts": "10.0.0.1[default]",
        "cmdbcollect_task_id": "267",
    }
    node_params.tags = {
        "instance_id": "cmdb_267",
        "instance_type": "cmdb_config_file",
        "collect_type": "http",
        "config_type": "config_file",
    }
    response = MagicMock(status_code=200, headers={"X-Task-Status": "queued"})
    pending_result = ({"config_file": {"status": "pending"}}, {"all": 0})

    with (
        patch("apps.cmdb.collection.collect_tasks.config_file_collect.CollectModels.objects.get", return_value=task),
        patch("apps.cmdb.collection.collect_tasks.config_file_collect.NodeParamsFactory.get_node_params", return_value=node_params),
        patch("apps.cmdb.collection.collect_tasks.config_file_collect.requests.get", return_value=response) as mock_get,
        patch("apps.cmdb.collection.collect_tasks.config_file_collect.ConfigFileService.build_pending_result", return_value=pending_result) as mock_pending,
    ):
        result = ConfigFileCollect(task.id)()

    assert result == pending_result
    mock_get.assert_called_once_with(
        "http://stargazer:8083/api/collect/collect_info",
        params={
            "plugin_name": "config_file_info",
            "hosts": "10.0.0.1[default]",
            "collect_task_id": "267",
        },
        headers={
            "X-Instance-ID": "cmdb_267",
            "X-Instance-Type": "cmdb_config_file",
            "X-Collect-Type": "http",
            "X-Config-Type": "config_file",
        },
        timeout=30,
    )
    mock_pending.assert_called_once_with(task)


def test_config_file_collect_raises_when_stargazer_does_not_accept_trigger():
    from apps.cmdb.collection.collect_tasks.config_file_collect import ConfigFileCollect

    task = SimpleNamespace(
        id=267,
        params={"config_file_path": "/opt/bk-lite/common.env"},
        instances=[{"inst_name": "10.0.0.1[default]"}],
        timeout=30,
    )
    node_params = MagicMock()
    node_params.custom_headers.return_value = {
        "cmdbplugin_name": "config_file_info",
        "cmdbhosts": "10.0.0.1[default]",
    }
    node_params.tags = {
        "instance_id": "cmdb_267",
        "instance_type": "cmdb_config_file",
        "collect_type": "http",
        "config_type": "config_file",
    }
    response = MagicMock(status_code=200, headers={"X-Task-Status": "failed"}, text="failed")

    with (
        patch("apps.cmdb.collection.collect_tasks.config_file_collect.CollectModels.objects.get", return_value=task),
        patch("apps.cmdb.collection.collect_tasks.config_file_collect.NodeParamsFactory.get_node_params", return_value=node_params),
        patch("apps.cmdb.collection.collect_tasks.config_file_collect.requests.get", return_value=response),
    ):
        try:
            ConfigFileCollect(task.id)()
        except BaseAppException as err:
            assert "配置文件采集触发失败" in str(err)
        else:
            raise AssertionError("Expected BaseAppException when trigger was not accepted")
