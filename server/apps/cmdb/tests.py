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
from rest_framework.exceptions import ValidationError

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

from apps.cmdb.constants.constants import VIEW
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.collect_tool_service import CollectToolService
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


def _response_json(response):
    return json.loads(response.content)


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
