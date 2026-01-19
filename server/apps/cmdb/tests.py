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