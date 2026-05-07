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

import os
import sys
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# 检查是否在Django环境中
if __name__ == "__main__":
    # 添加项目根目录到Python路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # 初始化Django环境
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
    import django
    django.setup()

from apps.cmdb.graph.drivers.graph_client import GraphClient
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


def test_import_model_config_applies_shared_post_import_extras():
    from apps.cmdb.services.model import ModelManage

    fake_file = MagicMock()
    fake_model_config = {"attr-host": [{"attr_id": "inst_name"}], "asso-host": []}

    with patch("apps.cmdb.services.model.ModelMigrate") as mock_migrator_cls, patch.object(
        ModelManage, "_apply_model_config_post_import_extras"
    ) as mock_apply_extras:
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
    with patch("apps.cmdb.management.commands.model_init.ModelMigrate") as mock_migrator_cls, patch(
        "apps.cmdb.management.commands.model_init.ModelManage._apply_model_config_post_import_extras"
    ) as mock_apply_extras:
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
    instance = {
        "_id": 1001,
        "model_id": "host",
        "inst_name": "host-a",
        "organization": [1],
        "_creator": "bob",
    }

    with patch(
        "apps.cmdb.views.instance.InstanceManage.query_entity_by_id",
        return_value=instance,
    ), patch.object(
        InstanceViewSet,
        "check_instance_permission",
        return_value=False,
    ) as mock_check_permission, patch(
        "apps.cmdb.views.instance.InstanceManage.instance_association_instance_list"
    ) as mock_association_list:
        response = InstanceViewSet().instance_association_instance_list(
            request,
            "host",
            1001,
        )

    assert response.status_code == 403
    assert json.loads(response.content)["result"] is False
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
                    logger.info(f"查询成功,返回原始结果")
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
    
    def query_relationships(self, src_label: str = "", rel_type: str = "", 
                          dst_label: str = "", limit: int = 10):
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


if __name__ == '__main__':
    query = "MATCH (n:k8s_test)  RETURN n ORDER BY ID(n) ASC"
    tester = CQLQueryTest()
    res = tester.query(query)
    for item in res:
        print(item)
