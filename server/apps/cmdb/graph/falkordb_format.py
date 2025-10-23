# -- coding: utf-8 --
# @File: falkordb_format.py
# @Time: 2025/8/29 16:25
# @Author: windyzhao
from typing import List, Dict, Any, Union
import json


class FormatDBResult:
    """
    处理 FalkorDB 查询结果格式的工具类
    """

    def __init__(self, result_set):
        """
        初始化

        Args:
            result_set: FalkorDB 查询返回的 result_set
        """
        self.result_set = result_set
        self.headers = []
        self.records = []

        if hasattr(result_set, 'header') and result_set.header:
            self.headers = [header[1] if isinstance(header, tuple) and len(header) > 1 else header
                            for header in result_set.header]

        if hasattr(result_set, 'result_set'):
            self.records = result_set.result_set

    def to_list_of_dicts(self) -> List[Dict[str, Any]]:
        """
        将结果转换为字典列表

        Returns:
            List[Dict]: 包含所有记录的字典列表
        """
        if not self.headers or not self.records:
            return []

        result = []
        for record in self.records:
            for value in record:
                result.append(self._format_value(value))

        return result

    def to_result_of_count(self):
        """
        将结果转换为计数字典列表

        Returns:
            List[Dict]: 包含计数结果的字典列表
        """

        result = {}
        for record in self.records:
            result[record[0]] = record[1]
        return result

    def to_list_of_lists(self) -> List[dict]:
        """
        将结果转换为列表的列表（包含表头）

        Returns:
            List[List]: 包含表头和数据的二维列表
        """
        result = []
        for record in self.records:
            result.extend([self._format_value(value) for value in record])
        return result

    def to_json(self, indent: int = 2) -> str:
        """
        将结果转换为 JSON 字符串

        Args:
            indent: JSON 缩进空格数

        Returns:
            str: JSON 格式的字符串
        """
        data = self.to_list_of_dicts()
        return json.dumps(data, indent=indent, ensure_ascii=False, default=str)

    def get_statistics(self) -> Dict[str, int]:
        """
        获取查询的统计信息

        Returns:
            Dict[str, int]: 统计信息字典
        """
        stats = {}
        if hasattr(self.result_set, 'get_statistics'):
            stats_obj = self.result_set.get_statistics()
            if stats_obj:
                stats = {
                    'nodes_created': getattr(stats_obj, 'nodes_created', 0),
                    'nodes_deleted': getattr(stats_obj, 'nodes_deleted', 0),
                    'relationships_created': getattr(stats_obj, 'relationships_created', 0),
                    'relationships_deleted': getattr(stats_obj, 'relationships_deleted', 0),
                    'properties_set': getattr(stats_obj, 'properties_set', 0),
                    'labels_added': getattr(stats_obj, 'labels_added', 0),
                    'labels_removed': getattr(stats_obj, 'labels_removed', 0),
                    'indices_created': getattr(stats_obj, 'indices_created', 0),
                    'indices_deleted': getattr(stats_obj, 'indices_deleted', 0),
                    'internal_execution_time': getattr(stats_obj, 'internal_execution_time', 0)
                }
        return stats

    def get_first_record(self) -> Dict[str, Any]:
        """
        获取第一条记录

        Returns:
            Dict: 第一条记录的字典
        """
        records = self.to_list_of_dicts()
        return records[0] if records else {}

    def get_column(self, column_name: str) -> List[Any]:
        """
        获取指定列的所有值

        Args:
            column_name: 列名

        Returns:
            List: 指定列的值列表
        """
        records = self.to_list_of_dicts()
        return [record.get(column_name) for record in records]

    def count(self) -> int:
        """
        获取记录数量

        Returns:
            int: 记录数量
        """
        return len(self.records)

    def is_empty(self) -> bool:
        """
        检查结果是否为空

        Returns:
            bool: 是否为空
        """
        return len(self.records) == 0

    def _format_value(self, value: Any) -> Any:
        """
        格式化值（处理节点、关系等特殊对象）

        Args:
            value: 原始值

        Returns:
            Any: 格式化后的值
        """
        if value is None:
            return None

        # 处理节点对象
        if hasattr(value, 'properties'):
            _id = getattr(value, 'id', "")
            labels = list(value.labels) if hasattr(value, 'labels') else []
            properties = dict(value.properties) if hasattr(value, 'properties') else {}
            properties['_id'] = _id
            properties['_labels'] = labels[0] if labels else ""
            return properties

        # 处理路径对象
        if hasattr(value, 'nodes') and hasattr(value, 'edges'):
            return {
                'type': 'path',
                'nodes': [self._format_value(node) for node in value.nodes],
                'relationships': [self._format_value(edge) for edge in value.edges]
            }

        return value

    def format_edge_to_list(self):
        result = []

        for record in self.records:
            for _re in record:
                edge_info = {
                    "src": {},
                    "edge": {},
                    "dst": {},
                }
                _edges = getattr(_re, '_edges', [])
                if not _edges:
                    continue

                _edge = _edges[0]
                _id = getattr(_edge, 'id', 0)
                properties = getattr(_edge, 'properties', {})
                properties['_id'] = _id
                edge_info["edge"] = _edge
                edge_info["edge"] = properties
                src_model = properties["src_model_id"]
                dst_model = properties["dst_model_id"]

                _nodes = getattr(_re, '_nodes', [])
                for _node in _nodes:
                    _id = getattr(_node, 'id', 0)
                    properties = getattr(_node, 'properties', {})
                    properties['_id'] = _id
                    if properties.get("model_id") == src_model:
                        edge_info["src"] = properties
                    elif properties.get("model_id") == dst_model:
                        edge_info["dst"] = properties

                result.append(edge_info)

        return result

    def __str__(self) -> str:
        """字符串表示"""
        return f"FormatDBResult(records={self.count()}, headers={self.headers})"

    def __repr__(self) -> str:
        """详细表示"""
        return f"FormatDBResult(headers={self.headers}, records_count={self.count()})"
