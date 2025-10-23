# -- coding: utf-8 --
# @File: falkordb.py
# @Time: 2025/8/29 14:48
# @Author: windyzhao
import os
import json
from typing import List, Union

from dotenv import load_dotenv
from falkordb import falkordb

from apps.cmdb.constants import INSTANCE, ModelConstraintKey
from apps.cmdb.graph.falkordb_format import FormatDBResult
from apps.cmdb.graph.format_type import FORMAT_TYPE
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

load_dotenv()


class FalkorDBConnectionPool:
    """FalkorDB连接池，避免重复初始化"""
    _instance = None
    _client = None
    _graph = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FalkorDBConnectionPool, cls).__new__(cls)
        return cls._instance

    def get_connection(self):
        """获取连接，如果未初始化则初始化"""
        if not self._initialized:
            self._initialize()
        return self._client, self._graph

    def _initialize(self):
        """初始化连接"""
        if self._initialized:
            return

        try:
            password = os.getenv("FALKORDB_REQUIREPASS", "") or None
            host = os.getenv('FALKORDB_HOST', '127.0.0.1')
            port = int(os.getenv("FALKORDB_PORT", "6379"))
            database = os.getenv("FALKORDB_DATABASE", "cmdb_graph")

            self._client = falkordb.FalkorDB(
                host=host,
                port=port,
                password=password
            )
            self._graph = self._client.select_graph(database)
            self._initialized = True
            logger.info(f"已连接到 FalkorDB，选择Graph: {database}")
        except Exception:
            import traceback
            logger.error(f"连接失败: {traceback.format_exc()}")
            raise


class FalkorDBClient:
    def __init__(self):
        self._pool = FalkorDBConnectionPool()
        self._client = None
        self._graph = None

    def connect(self):
        """建立连接并选择Graph"""
        try:
            self._client, self._graph = self._pool.get_connection()
            return True
        except Exception:  # noqa
            import traceback
            logger.error(f"连接失败: {traceback.format_exc()}")
            return False

    def close(self):
        """关闭连接"""
        if self._client:
            self._client = None
            self._graph = None

    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        # print("连接了FalkorDB")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        # self.close()
        pass

    # 析构函数（备用）
    def __del__(self):
        """对象销毁时自动关闭连接"""
        # self.close()
        pass

    def _execute_query(self, query: str):
        """
        统一的查询执行方法，记录CQL日志

        Args:
            query: CQL查询语句

        Returns:
            查询结果
        """
        import time
        start_time = time.time()

        # 记录查询日志
        logger.info(f"[CQL] {query}")

        try:
            result = self._graph.query(query)
            execution_time = (time.time() - start_time) * 1000  # 转换为毫秒
            logger.info(f"[CQL Result] 查询成功，耗时: {execution_time:.2f}ms")
            return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"[CQL Error] 查询失败，耗时: {execution_time:.2f}ms，错误: {str(e)}")
            raise

    def entity_to_list(self, data):
        """将使用fetchall查询的结果转换成列表类型"""
        _format = FormatDBResult(data)
        result = _format.to_list_of_lists()
        return [self.entity_to_dict(i, _format=False) for i in result]

    @staticmethod
    def entity_to_dict(data: dict, _format=True):
        """将使用single查询的结果转换成字典类型"""
        if _format:
            _format = FormatDBResult(data)
            result = _format.to_list_of_dicts()
            data = result[0] if result else {}
        return data

    @staticmethod
    def edge_to_list(data, return_entity: bool):
        """将使用fetchall查询的结果转换成列表类型"""
        _format = FormatDBResult(data)
        result = _format.format_edge_to_list()
        return result if return_entity else [i["edge"] for i in result]

    def edge_to_dict(self, data):
        """将使用single查询的结果转换成字典类型"""
        _data = self.entity_to_dict(data=data)
        return _data

    @staticmethod
    def escape_cql_string(value: str) -> str:
        """转义CQL字符串中的特殊字符"""
        if not isinstance(value, str):
            return value
        # 转义反斜杠和单引号
        return value.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def format_properties(properties: dict):
        """将属性格式化为CQL中的字符串格式，正确处理字符串转义"""
        properties_str = "{"
        for key, value in properties.items():
            if isinstance(value, str):
                escaped_value = FalkorDBClient.escape_cql_string(value)
                properties_str += f"{key}:'{escaped_value}',"
            else:
                properties_str += f"{key}:{value},"
        properties_str = properties_str[:-1]
        properties_str += "}"
        return properties_str

    def create_entity(
            self,
            label: str,
            properties: dict,
            check_attr_map: dict,
            exist_items: list,
            operator: str = None,
    ):
        """
        快速创建一个实体
        """
        result = self._create_entity(label, properties, check_attr_map, exist_items, operator)
        return result

    @staticmethod
    def check_unique_attr(item, check_attr_map, exist_items, is_update=False):
        """校验唯一属性"""
        not_only_attr = set()

        check_attrs = [i for i in check_attr_map.keys() if i in item] if is_update else check_attr_map.keys()

        for exist_item in exist_items:
            for attr in check_attrs:
                if exist_item[attr] == item[attr]:
                    not_only_attr.add(attr)

        if not not_only_attr:
            return

        message = ""
        for attr in not_only_attr:
            message += f"{check_attr_map[attr]} exist；"

        raise BaseAppException(message)

    def check_required_attr(self, item, check_attr_map, is_update=False):
        """校验必填属性"""
        not_required_attr = set()

        check_attrs = [i for i in check_attr_map.keys() if i in item] if is_update else check_attr_map.keys()

        for attr in check_attrs:
            if not item.get(attr):
                not_required_attr.add(attr)

        if not not_required_attr:
            return

        message = ""
        for attr in not_required_attr:
            # 记录必填项目为空
            message += f"{check_attr_map[attr]} is empty；"

        raise BaseAppException(message)

    def get_editable_attr(self, item, check_attr_map):
        """取可编辑属性"""
        return {k: v for k, v in item.items() if k in check_attr_map}

    def _create_entity(
            self,
            label: str,
            properties: dict,
            check_attr_map: dict,
            exist_items: list,
            operator: str = None,
    ):
        # 校验必填项标签非空
        if not label:
            raise BaseAppException("label is empty")

        # 校验唯一属性
        self.check_unique_attr(properties, check_attr_map.get("is_only", {}), exist_items)

        # 校验必填项
        self.check_required_attr(properties, check_attr_map.get("is_required", {}))

        # 补充创建人
        if operator:
            properties.update(_creator=operator)

        # 创建实体
        properties_str = self.format_properties(properties)
        entity = self._execute_query(f"CREATE (n:{label} {properties_str}) RETURN n")

        return self.entity_to_dict(entity)

    def create_edge(
            self,
            label: str,
            a_id: int,
            a_label: str,
            b_id: int,
            b_label: str,
            properties: dict,
            check_asst_key: str,
    ):
        """
        快速创建一条边
        """
        result = self._create_edge(label, a_id, a_label, b_id, b_label, properties, check_asst_key)
        return result

    def _create_edge(
            self,
            label: str,
            a_id: int,
            a_label: str,
            b_id: int,
            b_label: str,
            properties: dict,
            check_asst_key: str = "model_asst_id",
    ):
        # 校验必填项标签非空
        if not label:
            raise BaseAppException("label is empty")

        # 校验边是否已经存在
        check_asst_val = properties.get(check_asst_key)
        result = self._execute_query(
            f"MATCH (a:{a_label})-[e]-(b:{b_label}) WHERE ID(a) = {a_id} AND ID(b) = {b_id} AND e.{check_asst_key} = '{check_asst_val}' RETURN COUNT(e) AS count"
            # noqa
        )
        result = FormatDBResult(result).to_list_of_lists()
        edge_count = result[0] if result else 0
        if edge_count > 0:
            raise BaseAppException("edge already exists")

        # 创建边
        properties_str = self.format_properties(properties)
        edge = self._execute_query(
            f"MATCH (a:{a_label}) WHERE ID(a) = {a_id} WITH a MATCH (b:{b_label}) WHERE ID(b) = {b_id} CREATE (a)-[e:{label} {properties_str}]->(b) RETURN e"
            # noqa
        )

        return self.edge_to_dict(edge)

    def batch_create_entity(
            self,
            label: str,
            properties_list: list,
            check_attr_map: dict,
            exist_items: list,
            operator: str = None,
    ):
        """批量创建实体"""
        results = []
        for index, properties in enumerate(properties_list):
            result = {}
            try:
                entity = self._create_entity(label, properties, check_attr_map, exist_items, operator)
                result.update(data=entity, success=True, message="")
                exist_items.append(entity)
            except Exception as e:
                message = f"article {index + 1} data, {e}"
                result.update(message=message, success=False, data=properties)
            results.append(result)
        return results

    def batch_create_edge(
            self,
            label: str,
            a_label: str,
            b_label: str,
            edge_list: list,
            check_asst_key: str,
    ):
        """批量创建边"""
        results = []
        for index, edge_info in enumerate(edge_list):
            result = {}
            try:
                a_id = edge_info["src_id"]
                b_id = edge_info["dst_id"]
                edge = self._create_edge(label, a_id, a_label, b_id, b_label, edge_info, check_asst_key)
                result.update(data=edge, success=True)
            except Exception as e:
                message = f"article {index + 1} data, {e}"
                result.update(message=message, success=False)
            results.append(result)
        return results

    def format_search_params(self, params: list, param_type: str = "AND"):
        """
        查询参数格式化:
        bool: {"field": "is_host", "type": "bool", "value": True} -> "n.is_host = True"

        time: {"field": "create_time", "type": "time", "start": "", "end": ""} -> "n.time >= '2022-01-01 08:00:00' AND n.time <= '2022-01-02 08:00:00'"     # noqa

        str=: {"field": "name", "type": "str=", "value": "host"} -> "n.name = 'host'"
        str<>: {"field": "name", "type": "str<>", "value": "host"} -> "n.name <> 'host'"
        str*: {"field": "name", "type": "str*", "value": "host"} -> "n.name =~ '.*host.*'"
        str[]: {"field": "name", "type": "str[]", "value": ["host"]} -> "n.name IN ["host"]"

        int=: {"field": "mem", "type": "int=", "value": 200} -> "n.mem = 200"
        int>: {"field": "mem", "type": "int>", "value": 200} -> "n.mem > 200"
        int<: {"field": "mem", "type": "int<", "value": 200} -> "n.mem < 200"
        int<>: {"field": "mem", "type": "int<>", "value": 200} -> "n.mem <> 200"
        int[]: {"field": "mem", "type": "int[]", "value": [200]} -> "n.mem IN [200]"

        id=: {"field": "id", "type": "id=", "value": 115} -> "n(id) = 115"
        id[]: {"field": "id", "type": "id[]", "value": [115,116]} -> "n(id) IN [115,116]"

        list[]: {"field": "test", "type": "list[]", "value": [1,2]} -> "ANY(x IN value WHERE x IN n.test)"
        """

        params_str = ""
        param_type = f" {param_type} "
        for param in params:
            method = FORMAT_TYPE.get(param["type"])
            if not method:
                continue

            params_str += method(param)
            params_str += param_type

        return f"({params_str[:-len(param_type)]})" if params_str else params_str

    def format_final_params(self, search_params: list, search_param_type: str = "AND", permission_params=""):
        search_params_str = self.format_search_params(search_params, search_param_type)

        if not search_params_str:
            return permission_params

        if not permission_params:
            return search_params_str

        return f"{search_params_str} AND {permission_params}"

    def build_base_permission_filter(self,
                                     teams: list = None,
                                     inst_names: list = None,
                                     creator: str = None,
                                     model_id: str = None,
                                     additional_params: list = None,
                                     additional_param_type: str = "AND") -> str:
        """
        构建基础权限过滤条件

        Args:
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表  
            creator: 创建人用户名
            model_id: 模型ID (可选，用于进一步限制范围)
            additional_params: 额外的查询参数列表
            additional_param_type: 额外参数的连接类型 ("AND" 或 "OR")

        Returns:
            str: 完整的WHERE条件字符串 (不包含WHERE关键字)

        权限逻辑：
        1. 当前用户所在组织的数据: n.organization CONTAINS team_id
        2. 用户创建的在当前组织的数据: n._creator = 'username' 
        3. 特殊授予的实例数据(可以在别的组织): n.inst_name IN [...]
        """
        permission_conditions = []

        # 1. 组织权限：用户所在团队的数据
        if teams:
            team_conditions = []
            for team in teams:
                if team:  # 确保team不为空
                    # 处理团队数据，支持字典格式（如 {'id': 3}）和简单值
                    if isinstance(team, dict):
                        team_id = team.get('id') or team.get('team_id')
                        if team_id:
                            team_conditions.append(f"{team_id} IN n.organization")
                        else:
                            logger.warning(f"Team dict missing id field: {team}")
                    else:
                        team_conditions.append(f"{team} IN n.organization")

            if team_conditions:
                team_condition_str = " OR ".join(team_conditions)
                permission_conditions.append(f"({team_condition_str})")

        # 2. 创建人权限：用户创建的实例
        if creator:
            permission_conditions.append(f"n._creator = '{creator}'")

        # 3. 特殊实例权限：特殊授权的实例名称
        if inst_names:
            # 确保inst_names是有效的列表格式
            inst_names_list = [name for name in inst_names if name]  # 过滤空值
            if inst_names_list:
                permission_conditions.append(f"n.inst_name IN {inst_names_list}")

        # 组合权限条件 (使用OR，因为满足任一权限即可访问)
        base_permission_str = ""
        if permission_conditions:
            base_permission_str = " OR ".join(permission_conditions)
            base_permission_str = f"({base_permission_str})"

        # 5. 处理额外的查询参数
        additional_params_str = ""
        if additional_params:
            additional_params_str = self.format_search_params(additional_params, additional_param_type)

        # 6. 组合所有条件：权限条件 + 额外参数 + 模型限制
        conditions = []
        if base_permission_str:
            conditions.append(base_permission_str)
        if additional_params_str:
            conditions.append(additional_params_str)
        # 模型限制作为强制条件，而不是权限条件的一部分
        if model_id:
            conditions.append(f"n.model_id = '{model_id}'")

        final_condition = " AND ".join(conditions) if conditions else ""

        return final_condition

    def query_entity_with_permission(self,
                                     label: str,
                                     teams: list = None,
                                     inst_names: list = None,
                                     creator: str = None,
                                     model_id: str = None,
                                     search_params: list = None,
                                     search_param_type: str = "AND",
                                     page: dict = None,
                                     order: str = None,
                                     order_type: str = "ASC"):
        """
        带权限的实体查询 - 统一权限逻辑入口

        Args:
            label: 实体标签
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表
            creator: 创建人用户名
            model_id: 模型ID
            search_params: 搜索参数列表
            search_param_type: 搜索参数连接类型
            page: 分页参数 {"skip": 0, "limit": 10}
            order: 排序字段
            order_type: 排序类型 ("ASC" 或 "DESC")

        Returns:
            tuple: (实体列表, 总数)
        """
        label_str = f":{label}" if label else ""

        # 构建基础权限过滤条件
        where_condition = self.build_base_permission_filter(
            teams=teams,
            inst_names=inst_names,
            creator=creator,
            model_id=model_id,
            additional_params=search_params,
            additional_param_type=search_param_type
        )

        # 构建完整的SQL
        where_clause = f"WHERE {where_condition}" if where_condition else ""
        sql_str = f"MATCH (n{label_str}) {where_clause} RETURN n"

        # 排序
        sql_str += f" ORDER BY n.{order} {order_type}" if order else f" ORDER BY ID(n) {order_type}"

        # 分页查询
        count = None
        if page:
            count_str = f"MATCH (n{label_str}) {where_clause} RETURN COUNT(n) AS count"
            _result = self._execute_query(count_str)
            result = FormatDBResult(_result).to_list_of_lists()
            count = result[0] if result else 0
            sql_str += f" SKIP {page['skip']} LIMIT {page['limit']}"

        # 执行查询
        objs = self._execute_query(sql_str)
        return self.entity_to_list(objs), count

    def query_entity(
            self,
            label: str,
            params: list,
            page: dict = None,
            order: str = None,
            order_type: str = "ASC",
            param_type="AND",
            permission_params: str = "",
            permission_or_creator_filter: dict = None,
    ):
        """
        查询实体
        """
        label_str = f":{label}" if label else ""

        # 处理权限或创建人的OR条件
        if permission_or_creator_filter:
            inst_names = permission_or_creator_filter.get("inst_names", [])
            creator = permission_or_creator_filter.get("creator")

            # 构建OR条件：有权限的实例 OR 自己创建的实例
            or_conditions = []
            if inst_names:
                or_conditions.append(f"n.inst_name IN {inst_names}")
            if creator:
                or_conditions.append(f"n._creator = '{creator}'")
            # 结合权限参数
            if permission_params:
                or_conditions.append(permission_params)

            or_condition_str = " OR ".join(or_conditions)

            # 将OR条件与其他条件结合
            params_str = self.format_search_params(params, param_type=param_type)
            if params_str:
                params_str = f"({params_str}) AND ({or_condition_str})"
            else:
                params_str = f"({or_condition_str})"

        else:
            # 原有逻辑
            params_str = self.format_final_params(params, search_param_type=param_type,
                                                  permission_params=permission_params)

        params_str = f"WHERE {params_str}" if params_str else params_str

        sql_str = f"MATCH (n{label_str}) {params_str} RETURN n"

        # order by
        sql_str += f" ORDER BY n.{order} {order_type}" if order else f" ORDER BY ID(n) {order_type}"

        count_str = f"MATCH (n{label_str}) {params_str} RETURN COUNT(n) AS count"
        count = None
        if page:
            _result = self._execute_query(count_str)
            result = FormatDBResult(_result).to_list_of_lists()
            count = result[0] if result else 0
            sql_str += f" SKIP {page['skip']} LIMIT {page['limit']}"

        objs = self._execute_query(sql_str)
        return self.entity_to_list(objs), count

    def query_entity_by_id(self, id: int):
        """
        查询实体详情
        """
        obj = self._graph.query(f"MATCH (n) WHERE ID(n) = {id} RETURN n")
        if not obj:
            return {}
        return self.entity_to_dict(obj)

    def query_entity_by_ids(self, ids: list):
        """
        查询实体列表
        """
        objs = self._graph.query(f"MATCH (n) WHERE ID(n) IN {ids} RETURN n")
        if not objs:
            return []
        return self.entity_to_list(objs)

    def query_entity_by_inst_names(self, inst_names: list, model_id: str = None):
        """
        查询实体列表 通过实例名称
        """
        queries = f"AND n.model_id= '{model_id}'" if model_id else ""
        objs = self._graph.query(f"MATCH (n) WHERE n.inst_name IN {inst_names} {queries} RETURN n")
        if not objs:
            return []
        return self.entity_to_list(objs)

    def query_edge(
            self,
            label: str,
            params: list,
            param_type: str = "AND",
            return_entity: bool = False,
    ):
        """
        查询边
        """
        label_str = f":{label}" if label else ""
        params_str = self.format_search_params(params, param_type)
        params_str = f"WHERE {params_str}" if params_str else params_str

        objs = self._graph.query(f"MATCH p=(a)-[n{label_str}]->(b) {params_str} RETURN p")

        return self.edge_to_list(objs, return_entity)

    def query_edge_by_id(self, id: int, return_entity: bool = False):
        """
        查询边详情
        """
        objs = self._graph.query(f"MATCH p=(a)-[n]->(b) WHERE ID(n) = {id} RETURN p")
        edges = self.edge_to_list(objs, return_entity)
        return edges[0]

    def format_properties_set(self, properties: dict):
        """格式化properties的set数据，正确处理字符串转义"""
        properties_str = ""
        for key, value in properties.items():
            if isinstance(value, str):
                escaped_value = self.escape_cql_string(value)
                properties_str += f"n.{key}='{escaped_value}',"
            else:
                properties_str += f"n.{key}={value},"
        return properties_str if properties_str == "" else properties_str[:-1]

    def set_entity_properties(
            self,
            label: str,
            entity_ids: list,
            properties: dict,
            check_attr_map: dict,
            exist_items: list,
            check: bool = True,
    ):
        """
        设置实体属性
        """
        if check:
            # 校验唯一属性
            self.check_unique_attr(
                properties,
                check_attr_map.get("is_only", {}),
                exist_items,
                is_update=True,
            )

            # 校验必填项
            self.check_required_attr(properties, check_attr_map.get("is_required", {}), is_update=True)

            # 取出可编辑属性
            properties = self.get_editable_attr(properties, check_attr_map.get("editable", {}))

        nodes = self.batch_update_node_properties(label, entity_ids, properties)
        return self.entity_to_list(nodes)

    def batch_update_entity_properties(self,
                                       label: str,
                                       entity_ids: list,
                                       properties: dict,
                                       check_attr_map: dict,
                                       check: bool = True):
        """批量更新实体属性"""
        if check:
            # 校验必填项
            self.check_required_attr(properties, check_attr_map.get("is_required", {}), is_update=True)

            # 取出可编辑属性
            properties = self.get_editable_attr(properties, check_attr_map.get("editable", {}))
            if not properties:
                return []

        nodes = self.batch_update_node_properties(label, entity_ids, properties)
        return {"data": self.entity_to_list(nodes), "success": True, "message": ""}

    def batch_update_node_properties(self, label: str, node_ids: Union[int, List[int]], properties: dict):
        """批量更新节点属性"""
        label_str = f":{label}" if label else ""
        properties_str = self.format_properties_set(properties)
        if not properties_str:
            raise BaseAppException("properties is empty")
        nodes = self._graph.query(f"MATCH (n{label_str}) WHERE ID(n) IN {node_ids} SET {properties_str} RETURN n")
        return nodes

    def format_properties_remove(self, attrs: list):
        """格式化properties的remove数据"""
        properties_str = ""
        for attr in attrs:
            properties_str += f"n.{attr},"
        return properties_str if properties_str == "" else properties_str[:-1]

    def remove_entitys_properties(self, label: str, params: list, attrs: list):
        """移除某些实体的某些属性"""
        label_str = f":{label}" if label else ""
        properties_str = self.format_properties_remove(attrs)
        params_str = self.format_search_params(params)
        params_str = f"WHERE {params_str}" if params_str else params_str

        self._graph.query(f"MATCH (n{label_str}) {params_str} REMOVE {properties_str} RETURN n")

    def batch_delete_entity(self, label: str, entity_ids: list):
        """批量删除实体"""
        label_str = f":{label}" if label else ""
        self._graph.query(f"MATCH (n{label_str}) WHERE ID(n) IN {entity_ids} DETACH DELETE n")

    def detach_delete_entity(self, label: str, id: int):
        """删除实体，以及实体的关联关系"""
        label_str = f":{label}" if label else ""
        self._graph.query(f"MATCH (n{label_str}) WHERE ID(n) = {id} DETACH DELETE n")

    def delete_edge(self, edge_id: int):
        """删除边"""
        self._graph.query(f"MATCH ()-[n]->() WHERE ID(n) = {edge_id} DELETE n")

    def entity_objs(self, label: str, params: list, permission_params: str = ""):
        """实体对象查询"""

        label_str = f":{label}" if label else ""
        params_str = self.format_final_params(params, permission_params=permission_params)
        params_str = f"WHERE {params_str}" if params_str else params_str

        sql_str = f"MATCH (n{label_str}) {params_str} RETURN n"

        inst_objs = self._graph.query(sql_str)
        return inst_objs

    def query_topo(self, label: str, inst_id: int):
        """查询实例拓扑"""

        label_str = f":{label}" if label else ""
        params_str = self.format_search_params([{"field": "id", "type": "id=", "value": inst_id}])

        # 修复 FalkorDB 兼容性问题
        # 查询从指定节点出发的所有路径（作为源节点）
        if params_str:
            src_query = f"MATCH p=(n{label_str})-[*]->(m{label_str}) WHERE ID(n) = {inst_id} RETURN p"
        else:
            src_query = f"MATCH p=(n{label_str})-[*]->(m{label_str}) WHERE ID(n) = {inst_id} RETURN p"

        # 查询到指定节点的所有路径（作为目标节点）
        if params_str:
            dst_query = f"MATCH p=(m{label_str})-[*]->(n{label_str}) WHERE ID(n) = {inst_id} RETURN p"
        else:
            dst_query = f"MATCH p=(m{label_str})-[*]->(n{label_str}) WHERE ID(n) = {inst_id} RETURN p"

        try:
            src_objs = self._graph.query(src_query)
            dst_objs = self._graph.query(dst_query)
        except Exception as e:
            logger.error(f"Query topo failed: {e}")
            # 如果复杂查询失败，使用简单的直接关系查询
            return {}

        return dict(
            src_result=self.format_topo(inst_id, src_objs, True),
            dst_result=self.format_topo(inst_id, dst_objs, False)
        )

    @staticmethod
    def get_topo_config() -> dict:
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            topo_config_path = os.path.join(base_dir, "cmdb_config", "instance", "topo_config.json")

            if not os.path.isfile(topo_config_path):
                logger.warning("Topo config file not found: %s", topo_config_path)
                return {}

            with open(topo_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning("Topo config is not a dictionary: %s", topo_config_path)
                return {}
            return data

        except (OSError, json.JSONDecodeError) as e:
            logger.error("Failed to load topo config: %s, error: %s", topo_config_path, e)
            return {}

    def convert_to_cypher_match(self, label_str: str, model_id: str, params_str: str, dst: bool = True) -> str:
        """
        根据 JSON 配置生成 Neo4j Cypher 查询语句

        :param label_str: 节点标签
        :param model_id: 当前模型 ID
        :param params_str: WHERE 附加条件（字符串）
        :param dst: True 查询后继路径，False 查询前驱路径
        :return: 生成的 Cypher 查询语句
        """
        # 方向配置
        edge_type = "dst" if dst else "src"
        default_match = (
            f"MATCH p={f'(m{label_str})-[*]->(n{label_str})' if dst else f'(n{label_str})-[*]->(m{label_str})'} "
            f"WHERE 1=1 {params_str} RETURN p"
        )

        # 获取拓扑配置
        topo_path = self.get_topo_config().get(model_id)

        # 没有配置
        if not topo_path:
            return default_match

        edge_list = topo_path.get(edge_type)
        if not edge_list:
            return default_match

        cypher_parts = []
        node_aliases = {}
        rep_alias = ""

        # 为每一个关系生成相应的MATCH部分
        for i, relation in enumerate(edge_list):
            self_obj = relation['self_obj']
            target_obj = relation['target_obj']
            assoc = relation['assoc']

            # 处理self_obj
            if self_obj not in node_aliases:
                node_aliases[self_obj] = f'v{i}'
            self_alias = node_aliases[self_obj]

            # 添加self_obj节点
            if i == 0:
                if edge_type == "src":
                    rep_alias = self_alias
                cypher_parts.append(f"({self_alias}:instance {{model_id: '{self_obj}'}})")

            # 处理target_obj
            if target_obj not in node_aliases:
                node_aliases[target_obj] = f'v{i + 1}'
            target_alias = node_aliases[target_obj]
            if edge_type == "dst":
                rep_alias = target_alias
            # 添加关系和target_obj节点
            cypher_parts.append(f"-[:{assoc}]->({target_alias}:instance {{model_id: '{target_obj}'}})")

        # 拼接最终 MATCH
        match_path = "".join(cypher_parts)
        where_clause = f"WHERE 1=1 {params_str.replace('n', rep_alias)}"

        return f"MATCH p={match_path}\n{where_clause}\nRETURN p"

    def query_topo_test_config(self, label: str, inst_id: int, model_id: str):
        """查询实例拓扑"""
        label_str = f":{label}" if label else ""
        params_str = self.format_search_params([{"field": "id", "type": "id=", "value": inst_id}])
        if params_str:
            params_str = f"AND {params_str}"

        src_objs = self._graph.query(self.convert_to_cypher_match(label_str, model_id, params_str, dst=False))
        dst_objs = self._graph.query(self.convert_to_cypher_match(label_str, model_id, params_str, dst=True))

        return dict(
            src_result=self.format_topo(inst_id, src_objs, True),
            dst_result=self.format_topo(inst_id, dst_objs, False)
        )

    def format_topo(self, start_id, objs, entity_is_src=True):
        """格式化拓扑数据"""

        # 修复 FalkorDB QueryResult 对象检查方式
        all_results = objs.result_set

        edge_map = {}
        entity_map = {}

        for obj in all_results:
            for element in obj:
                # 分离出路径中的点和线
                nodes = getattr(element, "_nodes", [])  # 获取所有节点
                relationships = getattr(element, "_edges", [])  # 获取所有节点
                for node in nodes:
                    entity_map[node.id] = dict(_id=node.id, _label=node.labels[0], **node.properties)
                for relationship in relationships:
                    edge_map[relationship.id] = dict(
                        _id=relationship.id, _label=relationship.relation, **relationship.properties
                    )

        edges = list(edge_map.values())
        # 去除自己指向自己的边
        edges = [edge for edge in edges if edge["src_inst_id"] != edge["dst_inst_id"]]
        entities = list(entity_map.values())

        # 检查起始实体是否存在
        if start_id not in entity_map:
            return {}

        result = self.create_node(entity_map[start_id], edges, entities, entity_is_src)
        return result

    def create_node(self, entity, edges, entities, entity_is_src=True):
        """entity作为目标"""
        node = {
            "_id": entity["_id"],
            "model_id": entity["model_id"],
            "inst_name": entity["inst_name"],
            "children": [],
        }

        if entity_is_src:
            entity_key, child_entity_key = "src", "dst"
        else:
            entity_key, child_entity_key = "dst", "src"

        for edge in edges:
            if edge[f"{entity_key}_inst_id"] == entity["_id"]:
                child_entity = self.find_entity_by_id(edge[f"{child_entity_key}_inst_id"], entities)
                if child_entity:
                    child_node = self.create_node(child_entity, edges, entities, entity_is_src)
                    child_node["model_asst_id"] = edge["model_asst_id"]
                    child_node["asst_id"] = edge["asst_id"]
                    node["children"].append(child_node)
        return node

    def find_entity_by_id(self, entity_id, entities):
        """根据ID找实体"""
        for entity in entities:
            if entity["_id"] == entity_id:
                return entity
        return None

    @staticmethod
    def format_instance_permission_params(instance_permission_params: list, created: str = ""):
        model_list = []
        instance_conditions = []
        for perm_param in instance_permission_params:
            model_id = perm_param.get('model_id')
            instance_names = perm_param.get('inst_names', [])
            if model_id and instance_names:
                # 对于有具体实例权限的模型，只统计指定的实例
                condition = f"(n.model_id = '{model_id}' AND n.inst_name IN {instance_names})"
                instance_conditions.append(condition)
                model_list.append(model_id)

        # 如果有模型ID但没有实例名称，则只统计该模型的所有实例
        instance_condition_str = " OR ".join(instance_conditions) if instance_conditions else ""

        # 只有在存在具体模型限制时才排除其他模型
        if model_list and instance_conditions:
            instance_condition_str += f" OR (NOT n.model_id IN {model_list})"

        # 判断是否为全部权限：没有具体的实例限制条件
        has_full_permission = not instance_conditions and not model_list

        # 个人创建的过滤 - 只有在没有全部权限时才添加
        if created and not has_full_permission:
            if instance_condition_str:
                instance_condition_str += f" OR (n._creator = '{created}')"
            else:
                instance_condition_str = f"n._creator = '{created}'"

        return instance_condition_str

    def entity_count(self, label: str, group_by_attr: str, params: list, permission_params: str = "",
                     inst_name_params: str = "", created: str = ""):

        label_str = f":{label}" if label else ""

        or_filters = []

        if permission_params:
            or_filters.append(permission_params)
        if inst_name_params:
            or_filters.append(inst_name_params)

        filter_str = "WHERE "

        if or_filters:
            or_condition = " OR ".join(or_filters)
            filter_str += f"({or_condition})"

        if created:
            params.append({"field": "_creator", "type": "str=", "value": created})

        if params:
            params_str = self.format_search_params(params)
            if or_filters:
                filter_str += f" AND ({params_str})"
            else:
                filter_str += f" {params_str}"

        count_sql = f"MATCH (n{label_str}) {filter_str} RETURN n.{group_by_attr} AS {group_by_attr}, COUNT(n) AS count"
        data = self._graph.query(count_sql)
        result = FormatDBResult(data).to_result_of_count()
        return result

    def full_text(self, search: str, permission_params: str = "", inst_name_params: str = "", created: str = ""):
        """全文检索"""

        # 构建过滤条件
        conditions = []

        # 添加权限和实例名称过滤条件
        or_filters = []
        if permission_params:
            or_filters.append(permission_params)
        if inst_name_params:
            or_filters.append(inst_name_params)

        if or_filters:
            or_condition = " OR ".join(or_filters)
            conditions.append(f"({or_condition})")

        # 添加创建者过滤条件
        if created:
            params = [{"field": "_creator", "type": "str=", "value": created}]
            params_str = self.format_search_params(params)
            if params_str:
                conditions.append(params_str)

        # 添加全文检索条件
        escaped_search = self.escape_cql_string(search)
        search_condition = f"ANY(key IN keys(n) WHERE key <> 'organization' AND n[key] IS NOT NULL AND toString(n[key]) CONTAINS '{escaped_search}')"
        conditions.append(search_condition)

        # 构建完整WHERE子句
        where_clause = " AND ".join(conditions) if conditions else "true"
        query = f"""MATCH (n:{INSTANCE}) WHERE {where_clause} RETURN n"""

        try:
            objs = self._graph.query(query)
            return self.entity_to_list(objs)
        except Exception as e:
            logger.error(f"Full text search failed: {e}")
            # 如果还是失败，使用最简单的方案：只搜索特定的字符串字段
            try:
                # 重新构建简化的条件列表（不包含复杂的ANY条件）
                simple_conditions = []

                # 保留权限和创建者过滤条件
                if or_filters:
                    or_condition = " OR ".join(or_filters)
                    simple_conditions.append(f"({or_condition})")

                if created:
                    params = [{"field": "_creator", "type": "str=", "value": created}]
                    params_str = self.format_search_params(params)
                    if params_str:
                        simple_conditions.append(params_str)

                # 添加简化的搜索条件
                simple_search_condition = f"(n.inst_name CONTAINS '{escaped_search}' OR n.model_id CONTAINS '{escaped_search}' OR toString(n._id) CONTAINS '{escaped_search}')"
                simple_conditions.append(simple_search_condition)

                simple_where_clause = " AND ".join(simple_conditions) if simple_conditions else "true"
                fallback_query = f"""MATCH (n:{INSTANCE}) WHERE {simple_where_clause} RETURN n"""

                objs = self._graph.query(fallback_query)
                return self.entity_to_list(objs)
            except Exception as fallback_e:
                logger.error(f"Fallback full text search also failed: {fallback_e}")
                return []

    def batch_save_entity(
            self,
            label: str,
            properties_list: list,
            check_attr_map: dict,
            exist_items: list,
            operator: str = None,
    ):
        """批量保存实体，支持新增与更新"""
        unique_key = check_attr_map.get(ModelConstraintKey.unique.value, {}).keys()
        add_nodes = []
        update_results = []
        if unique_key:
            properties_map = {}
            for properties in properties_list:
                properties_key = tuple([properties.get(k) for k in unique_key if k in properties])
                # 对参数中的节点按唯一键进行去重
                properties_map[properties_key] = properties
            # 已有节点处理
            item_map = {}
            for item in exist_items:
                item_key = tuple([item.get(k) for k in unique_key if k in item])
                item_map[item_key] = item
            for properties_key, properties in properties_map.items():
                node = item_map.get(properties_key)
                if node:
                    # 节点更新
                    try:
                        results = self.batch_update_entity_properties(label=label, entity_ids=[node.get("_id")],
                                                                      properties=properties,
                                                                      check_attr_map=check_attr_map)
                        results["data"] = results["data"][0]
                        update_results.append(results)
                    except Exception as e:
                        logger.info(f"update entity error: {e}")
                        update_results.append({"success": False, "data": properties, "message": "update entity error"})

                else:
                    # 暂存统一新增
                    add_nodes.append(properties)
        else:
            add_nodes = properties_list
        add_results = self.batch_create_entity(label=label, properties_list=add_nodes, check_attr_map=check_attr_map,
                                               exist_items=exist_items, operator=operator)
        return add_results, update_results

    def count_entity_with_permission(self,
                                     label: str,
                                     group_by_attr: str,
                                     teams: list = None,
                                     inst_names: list = None,
                                     creator: str = None,
                                     model_id: str = None,
                                     search_params: list = None,
                                     search_param_type: str = "AND"):
        """
        带权限的实体统计查询

        Args:
            label: 实体标签
            group_by_attr: 分组统计的属性
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表
            creator: 创建人用户名
            model_id: 模型ID
            search_params: 额外搜索参数
            search_param_type: 搜索参数连接类型

        Returns:
            list: 统计结果 [{"attr_value": "value", "count": 10}, ...]
        """
        label_str = f":{label}" if label else ""

        # 构建基础权限过滤条件
        where_condition = self.build_base_permission_filter(
            teams=teams,
            inst_names=inst_names,
            creator=creator,
            model_id=model_id,
            additional_params=search_params,
            additional_param_type=search_param_type
        )

        where_clause = f"WHERE {where_condition}" if where_condition else ""
        count_sql = f"MATCH (n{label_str}) {where_clause} RETURN n.{group_by_attr} AS {group_by_attr}, COUNT(n) AS count"

        data = self._graph.query(count_sql)
        result = FormatDBResult(data).to_result_of_count()
        return result

    def fulltext_search_with_permission(self,
                                        search: str,
                                        teams: list = None,
                                        inst_names: list = None,
                                        creator: str = None,
                                        model_id: str = None,
                                        search_params: list = None,
                                        search_param_type: str = "AND"):
        """
        带权限的全文检索

        Args:
            search: 搜索关键词
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表
            creator: 创建人用户名
            model_id: 模型ID
            search_params: 额外搜索参数
            search_param_type: 搜索参数连接类型

        Returns:
            list: 搜索结果实体列表
        """
        # 构建基础权限过滤条件
        permission_condition = self.build_base_permission_filter(
            teams=teams,
            inst_names=inst_names,
            creator=creator,
            model_id=model_id,
            additional_params=search_params,
            additional_param_type=search_param_type
        )

        # 构建全文检索条件
        search_condition = f"ANY(key IN keys(n) WHERE key <> 'organization' AND n[key] IS NOT NULL AND toString(n[key]) CONTAINS '{search}')"

        # 组合权限和搜索条件
        where_conditions = []
        if permission_condition:
            where_conditions.append(f"({permission_condition})")
        if search_condition:
            where_conditions.append(f"({search_condition})")

        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
        query = f"MATCH (n:{INSTANCE}) {where_clause} RETURN n"

        try:
            objs = self._graph.query(query)
            return self.entity_to_list(objs)
        except Exception as e:
            logger.error(f"Full text search with permission failed: {e}")
            # 降级到简单搜索
            try:
                fallback_condition = f"n.inst_name CONTAINS '{search}'"
                if permission_condition:
                    fallback_condition = f"({permission_condition}) AND ({fallback_condition})"

                fallback_query = f"MATCH (n:{INSTANCE}) WHERE {fallback_condition} RETURN n"
                objs = self._graph.query(fallback_query)
                return self.entity_to_list(objs)
            except Exception as fallback_e:
                logger.error(f"Fallback search also failed: {fallback_e}")
                return []

    def export_entities_with_permission(self,
                                        label: str,
                                        teams: list = None,
                                        inst_names: list = None,
                                        creator: str = None,
                                        model_id: str = None,
                                        inst_ids: list = None,
                                        search_params: list = None,
                                        search_param_type: str = "AND"):
        """
        带权限的实体导出查询

        Args:
            label: 实体标签
            teams: 用户所在的团队列表
            inst_names: 特殊授权的实例名称列表
            creator: 创建人用户名
            model_id: 模型ID
            inst_ids: 指定要导出的实例ID列表 (在权限范围内进行过滤)
            search_params: 额外搜索参数
            search_param_type: 搜索参数连接类型

        Returns:
            list: 符合权限和条件的实体列表
        """
        # 如果指定了实例ID，将其作为额外的搜索参数
        final_search_params = search_params or []
        if inst_ids:
            final_search_params.append({
                "field": "id",
                "type": "id[]",
                "value": inst_ids
            })

        # 使用统一的权限查询方法
        entities, _ = self.query_entity_with_permission(
            label=label,
            teams=teams,
            inst_names=inst_names,
            creator=creator,
            model_id=model_id,
            search_params=final_search_params,
            search_param_type=search_param_type
        )

        return entities
