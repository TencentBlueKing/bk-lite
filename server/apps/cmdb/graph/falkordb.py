# -- coding: utf-8 --
# @File: falkordb.py
# @Time: 2025/8/29 14:48
# @Author: windyzhao
import os
import time
import json
from typing import List, Union

from dotenv import load_dotenv
from falkordb import falkordb

from apps.cmdb.constants.constants import INSTANCE, ModelConstraintKey
from apps.cmdb.graph.falkordb_format import FormatDBResult
from apps.cmdb.graph.format_type import (
    FORMAT_TYPE,
    ParameterCollector,
    FORMAT_TYPE_PARAMS,
)
from apps.cmdb.graph.validators import CQLValidator
from apps.cmdb.display_field import ExcludeFieldsCache
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
            host = os.getenv("FALKORDB_HOST", "127.0.0.1")
            port = int(os.getenv("FALKORDB_PORT", "6379"))
            database = os.getenv("FALKORDB_DATABASE", "cmdb_graph")

            self._client = falkordb.FalkorDB(host=host, port=port, password=password)
            self._graph = self._client.select_graph(database)
            self._initialized = True
            logger.info(f"已连接到 FalkorDB，选择Graph: {database}")
        except Exception:
            import traceback

            logger.error(f"连接失败: {traceback.format_exc()}")
            raise


class FalkorDBClient:
    # 参数化查询开关（可通过环境变量控制）
    ENABLE_PARAMETERIZATION = True

    def __init__(self):
        self._pool = FalkorDBConnectionPool()
        self._client = None
        self._graph = None
        # 初始化参数收集器
        self._param_collector = ParameterCollector()

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

    def _execute_query(self, query: str, params: dict = None):
        """
        统一的查询执行方法，支持参数化查询

        Args:
            query: CQL查询语句
            params: 查询参数字典（可选）

        Returns:
            查询结果
        """
        start_time = time.time()

        # 记录查询日志
        logger.debug(f"[CQL Query] {query}")
        if params:
            # 脱敏参数日志
            safe_params = {
                k: "***" if "password" in k.lower() else v for k, v in params.items()
            }
            logger.debug(f"[CQL Params] {safe_params}")

        try:
            # 根据是否有参数选择调用方式
            if params:
                result = self._graph.query(query, params=params)
            else:
                result = self._graph.query(query)

            execution_time = (time.time() - start_time) * 1000  # 转换为毫秒
            logger.debug(f"[CQL Result] 查询成功，耗时: {execution_time:.2f}ms")
            return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(
                f"[CQL Error] 查询失败，耗时: {execution_time:.2f}ms，错误: {str(e)}"
            )
            raise

    def entity_to_list(self, data):
        """将使用fetchall查询的结果转换成列表类型"""
        _format = FormatDBResult(data)
        result = _format.to_list_of_lists()
        return [self.entity_to_dict(i, _format=False) for i in result]

    @staticmethod
    def entity_to_dict(data: dict, _format=True):
        """将使用single查询的结果转换成字典类型，过滤以_display结尾的字段"""
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

    @staticmethod
    def _build_exclude_fields_list(exclude_fields: list) -> str:
        """Defense-in-depth: Validate exclude_fields from cache before query interpolation."""
        if not exclude_fields:
            return "[]"

        validated_fields = []
        for field in exclude_fields:
            try:
                validated_field = CQLValidator.validate_field(field)
                validated_fields.append(f"'{validated_field}'")
            except Exception as e:
                logger.warning(f"[全文检索] 排除字段验证失败，跳过: {field}, 原因: {e}")
                continue

        return "[" + ", ".join(validated_fields) + "]"

    def format_properties_params(self, properties: dict):
        """
        将属性字典转换为参数化查询的参数

        FalkorDB 支持使用 Map 参数: CREATE (n:Label $props)
        参考: https://docs.falkordb.com/cypher_support.html#parameters

        Args:
            properties: 属性字典

        Returns:
            dict: 参数字典,格式为 {'props': properties}
        """
        if not properties:
            return {}

        # 验证所有字段名是否合法
        validated_props = {}
        for key, value in properties.items():
            validated_field = CQLValidator.validate_field(key)
            if validated_field:
                validated_props[validated_field] = value

        return {"props": validated_props} if validated_props else {}

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
        result = self._create_entity(
            label, properties, check_attr_map, exist_items, operator
        )
        return result

    @staticmethod
    def check_unique_attr(item, check_attr_map, exist_items, is_update=False):
        """校验唯一属性"""
        not_only_attr = set()

        check_attrs = (
            [i for i in check_attr_map.keys() if i in item]
            if is_update
            else check_attr_map.keys()
        )

        for exist_item in exist_items:
            for attr in check_attrs:
                if exist_item.get(attr) == item[attr]:
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

        check_attrs = (
            [i for i in check_attr_map.keys() if i in item]
            if is_update
            else check_attr_map.keys()
        )

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
        # 验证标签（不能参数化）
        validated_label = CQLValidator.validate_label(label)
        if not validated_label:
            raise BaseAppException("label is empty")

        # 校验唯一属性
        self.check_unique_attr(
            properties, check_attr_map.get("is_only", {}), exist_items
        )

        # 校验必填项
        self.check_required_attr(properties, check_attr_map.get("is_required", {}))

        # 补充创建人
        if operator:
            properties = {**properties, "_creator": operator}

        # 创建实体
        if self.ENABLE_PARAMETERIZATION:
            # 参数化: CREATE + SET += 以支持 list 类型属性
            # inline map (CREATE (n $props)) 不支持 list 类型,必须用运行时赋值
            props_params = self.format_properties_params(properties)
            query = f"CREATE (n:{validated_label}) SET n += $props RETURN n"
            entity = self._execute_query(query, params=props_params)
        else:
            # 旧逻辑
            properties_str = self.format_properties(properties)
            query = f"CREATE (n:{validated_label} {properties_str}) RETURN n"
            entity = self._execute_query(query)

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
        result = self._create_edge(
            label, a_id, a_label, b_id, b_label, properties, check_asst_key
        )
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
        # 验证标签和关系类型
        validated_label = CQLValidator.validate_relation(label)
        validated_a_label = CQLValidator.validate_label(a_label)
        validated_b_label = CQLValidator.validate_label(b_label)
        validated_check_key = CQLValidator.validate_field(check_asst_key)

        if not validated_label:
            raise BaseAppException("label is empty")

        # 验证ID
        validated_a_id = CQLValidator.validate_id(a_id)
        validated_b_id = CQLValidator.validate_id(b_id)

        # 校验边是否已经存在
        check_asst_val = properties.get(check_asst_key)

        if self.ENABLE_PARAMETERIZATION:
            # 参数化查询检查边是否存在
            check_query = (
                f"MATCH (a:{validated_a_label})-[e]-(b:{validated_b_label}) "
                f"WHERE ID(a) = $a_id AND ID(b) = $b_id AND e.{validated_check_key} = $check_val "
                f"RETURN COUNT(e) AS count"
            )
            check_params = {
                "a_id": validated_a_id,
                "b_id": validated_b_id,
                "check_val": check_asst_val,
            }
            result = self._execute_query(check_query, params=check_params)
        else:
            # 旧逻辑
            result = self._execute_query(
                f"MATCH (a:{validated_a_label})-[e]-(b:{validated_b_label}) WHERE ID(a) = {validated_a_id} AND ID(b) = {validated_b_id} AND e.{validated_check_key} = '{check_asst_val}' RETURN COUNT(e) AS count"
            )

        result = FormatDBResult(result).to_list_of_lists()
        edge_count = result[0] if result else 0
        if edge_count > 0:
            raise BaseAppException("edge already exists")

        # 创建边
        if self.ENABLE_PARAMETERIZATION:
            # 参数化: CREATE + SET += 以支持 list 类型属性
            # inline map (CREATE (a)-[e $props]->(b)) 不支持 list 类型,必须用运行时赋值
            props_params = self.format_properties_params(properties)
            # 合并所有参数
            all_params = {
                "a_id": validated_a_id,
                "b_id": validated_b_id,
                **props_params,
            }
            create_query = (
                f"MATCH (a:{validated_a_label}) WHERE ID(a) = $a_id "
                f"WITH a MATCH (b:{validated_b_label}) WHERE ID(b) = $b_id "
                f"CREATE (a)-[e:{validated_label}]->(b) SET e += $props RETURN e"
            )
            edge = self._execute_query(create_query, params=all_params)
        else:
            # 旧逻辑
            properties_str = self.format_properties(properties)
            edge = self._execute_query(
                f"MATCH (a:{validated_a_label}) WHERE ID(a) = {validated_a_id} WITH a MATCH (b:{validated_b_label}) WHERE ID(b) = {validated_b_id} CREATE (a)-[e:{validated_label} {properties_str}]->(b) RETURN e"
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
                entity = self._create_entity(
                    label, properties, check_attr_map, exist_items, operator
                )
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
                edge = self._create_edge(
                    label, a_id, a_label, b_id, b_label, edge_info, check_asst_key
                )
                result.update(data=edge, success=True)
            except Exception as e:
                message = f"article {index + 1} data, {e}"
                result.update(message=message, success=False)
            results.append(result)
        return results

    def format_search_params(
        self,
        params: list,
        param_type: str = "AND",
        param_collector: ParameterCollector = None,
        case_sensitive: bool = True,
    ):
        """
        查询参数格式化（参数化版本）

        Args:
            params: 参数列表
            param_type: 连接类型（AND/OR）
            param_collector: 可选的参数收集器。如果提供则使用它（累积参数），否则使用实例收集器（独立查询）
            case_sensitive: 是否区分大小写（仅对 str* 类型生效）

        Returns:
            str: 条件字符串（参数存入 collector）
        """
        # 使用传入的 collector 或实例 collector
        collector = (
            param_collector if param_collector is not None else self._param_collector
        )

        # 如果使用实例 collector 且没有传入外部 collector，重置它（独立查询）
        if (
            collector is self._param_collector
            and param_collector is None
            and self.ENABLE_PARAMETERIZATION
        ):
            collector.reset()

        params_conditions = []
        for param in params:
            param_format_type = param.get("type")
            if not param_format_type:
                continue

            if self.ENABLE_PARAMETERIZATION:
                method = FORMAT_TYPE_PARAMS.get(param_format_type)
                if method:
                    param_with_context = {**param, "case_sensitive": case_sensitive}
                    condition = method(param_with_context, collector)
                    if condition:
                        params_conditions.append(condition)
            else:
                method = FORMAT_TYPE.get(param_format_type)
                if method:
                    condition = method(param)
                    if condition:
                        params_conditions.append(condition)

        if not params_conditions:
            return "", {}

        params_str = f" {param_type} ".join(params_conditions)
        final_str = f"({params_str})" if params_str else ""

        return final_str, collector.get_params() if self.ENABLE_PARAMETERIZATION else {}

    def format_final_params(
        self, search_params: list, search_param_type: str = "AND", permission_params=""
    ):
        """格式化最终参数"""
        search_params_str, _ = self.format_search_params(
            search_params, search_param_type
        )

        if not search_params_str:
            return permission_params

        if not permission_params:
            return search_params_str

        return f"{search_params_str} AND {permission_params}"

    def query_entity(
        self,
        label: str,
        params: list,
        format_permission_dict: dict = {},
        page: dict = None,
        order: str = None,
        order_type: str = "ASC",
        param_type="AND",
        organization_field: str = "organization",
        case_sensitive: bool = True,
    ):
        """
        查询实体（参数化版本）
        params: 查询参数列表 固定
        format_permission_dict：组织权限查询参数 dict
        """
        # 验证标签和排序类型
        validated_label = CQLValidator.validate_label(label) if label else ""
        validated_order_type = CQLValidator.validate_order_type(order_type)

        label_str = f":{validated_label}" if validated_label else ""

        # 创建统一的参数收集器,避免多次调用时参数覆盖
        param_collector = ParameterCollector() if self.ENABLE_PARAMETERIZATION else None

        # 使用参数化的format_search_params（传入统一的收集器）
        base_params_str, _ = self.format_search_params(
            params,
            param_type=param_type,
            param_collector=param_collector,
            case_sensitive=case_sensitive,
        )

        # 构建权限参数（参数化，使用同一个收集器）
        permission_filters = []
        for organization_id, query_list in format_permission_dict.items():
            # 组织查询参数化
            organization_query = [
                {
                    "field": organization_field,
                    "type": "list[]",
                    "value": [organization_id],
                }
            ]
            org_base_permission_str, _ = self.format_search_params(
                organization_query,
                param_type="AND",
                param_collector=param_collector,
                case_sensitive=case_sensitive,
            )

            org_permission_str, _ = self.format_search_params(
                query_list,
                param_type="OR",
                param_collector=param_collector,
                case_sensitive=case_sensitive,
            )

            # 调试日志
            logger.debug(
                f"[query_entity] org_id={organization_id}, query_list={query_list}"
            )
            logger.debug(
                f"[query_entity] org_base={org_base_permission_str}, org_perm={org_permission_str}"
            )

            # 组合组织条件（避免多余括号）
            org_filters = []
            if org_base_permission_str:
                org_filters.append(org_base_permission_str)
            if org_permission_str:
                # org_permission_str 已经包含括号(如 (cond1 OR cond2))，直接使用
                org_filters.append(org_permission_str)

            if org_filters:
                # 单个条件不需要额外括号
                if len(org_filters) == 1:
                    permission_filters.append(org_filters[0])
                else:
                    # 多个条件用 AND 连接时需要括号保证优先级
                    combined_filter = f"({' AND '.join(org_filters)})"
                    permission_filters.append(combined_filter)

        # 从统一的收集器获取所有参数
        query_params = param_collector.get_params() if param_collector else {}

        # 组合最终查询条件
        final_conditions = []
        if permission_filters:
            # 单个权限条件不需要额外括号
            if len(permission_filters) == 1:
                final_conditions.append(permission_filters[0])
            else:
                # 多个权限条件用 OR 连接时需要括号
                permission_str = " OR ".join(permission_filters)
                final_conditions.append(f"({permission_str})")
        if base_params_str:
            final_conditions.append(base_params_str)

        final_params_str = " AND ".join(final_conditions) if final_conditions else ""
        params_str = f"WHERE {final_params_str}" if final_params_str else ""

        sql_str = f"MATCH (n{label_str}) {params_str} RETURN n"

        # 调试日志：打印 query_entity 的查询
        logger.debug(f"[query_entity] SQL: {sql_str}")
        logger.debug(f"[query_entity] Params: {query_params}")
        logger.debug(f"[query_entity] format_permission_dict: {format_permission_dict}")

        # 排序
        if order:
            validated_order = CQLValidator.validate_field(order)
            sql_str += f" ORDER BY n.{validated_order} {validated_order_type}"
        else:
            sql_str += f" ORDER BY ID(n) {validated_order_type}"

        # 分页
        count = None
        if page:
            count_str = f"MATCH (n{label_str}) {params_str} RETURN COUNT(n) AS count"
            _result = self._execute_query(
                count_str, params=query_params if self.ENABLE_PARAMETERIZATION else None
            )
            result = FormatDBResult(_result).to_list_of_lists()
            count = result[0] if result else 0
            sql_str += f" SKIP {page['skip']} LIMIT {page['limit']}"

        objs = self._execute_query(
            sql_str, params=query_params if self.ENABLE_PARAMETERIZATION else None
        )
        return self.entity_to_list(objs), count

    def query_entity_by_id(self, id: int):
        """
        查询实体详情（参数化版本）
        """
        validated_id = CQLValidator.validate_id(id)

        if self.ENABLE_PARAMETERIZATION:
            query = "MATCH (n) WHERE ID(n) = $id RETURN n"
            params = {"id": validated_id}
            obj = self._execute_query(query, params=params)
        else:
            query = f"MATCH (n) WHERE ID(n) = {validated_id} RETURN n"
            obj = self._execute_query(query)

        if not obj:
            return {}
        return self.entity_to_dict(obj)

    def query_entity_by_ids(self, ids: list):
        """
        查询实体列表（参数化版本）
        """
        validated_ids = CQLValidator.validate_ids(ids)

        if self.ENABLE_PARAMETERIZATION:
            query = "MATCH (n) WHERE ID(n) IN $ids RETURN n"
            params = {"ids": validated_ids}
            objs = self._execute_query(query, params=params)
        else:
            query = f"MATCH (n) WHERE ID(n) IN {validated_ids} RETURN n"
            objs = self._execute_query(query)

        if not objs:
            return []
        return self.entity_to_list(objs)

    def query_entity_by_inst_names(self, inst_names: list, model_id: str = None):
        """
        查询实体列表 通过实例名称（参数化版本）
        """
        if self.ENABLE_PARAMETERIZATION:
            params = {"inst_names": inst_names}
            queries = ""
            if model_id:
                params["model_id"] = model_id
                queries = "AND n.model_id = $model_id"

            query = f"MATCH (n) WHERE n.inst_name IN $inst_names {queries} RETURN n"
            objs = self._execute_query(query, params=params)
        else:
            queries = f"AND n.model_id= '{model_id}'" if model_id else ""
            objs = self._execute_query(
                f"MATCH (n) WHERE n.inst_name IN {inst_names} {queries} RETURN n"
            )

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
        查询边（参数化版本）
        """
        validated_label = CQLValidator.validate_label(label) if label else ""
        label_str = f":{validated_label}" if validated_label else ""

        params_str, query_params = self.format_search_params(params, param_type)
        params_str = f"WHERE {params_str}" if params_str else params_str

        query = f"MATCH p=(a)-[n{label_str}]->(b) {params_str} RETURN p"
        objs = self._execute_query(
            query, params=query_params if self.ENABLE_PARAMETERIZATION else None
        )

        return self.edge_to_list(objs, return_entity)

    def query_edge_by_id(self, id: int, return_entity: bool = False):
        """
        查询边详情（参数化版本）
        """
        validated_id = CQLValidator.validate_id(id)

        if self.ENABLE_PARAMETERIZATION:
            query = "MATCH p=(a)-[n]->(b) WHERE ID(n) = $id RETURN p"
            params = {"id": validated_id}
            objs = self._execute_query(query, params=params)
        else:
            objs = self._execute_query(
                f"MATCH p=(a)-[n]->(b) WHERE ID(n) = {validated_id} RETURN p"
            )

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
            self.check_required_attr(
                properties, check_attr_map.get("is_required", {}), is_update=True
            )

            # 取出可编辑属性
            properties = self.get_editable_attr(
                properties, check_attr_map.get("editable", {})
            )

        nodes = self.batch_update_node_properties(label, entity_ids, properties)
        return self.entity_to_list(nodes)

    def batch_update_entity_properties(
        self,
        label: str,
        entity_ids: list,
        properties: dict,
        check_attr_map: dict,
        check: bool = True,
    ):
        """批量更新实体属性"""
        if check:
            # 校验必填项
            self.check_required_attr(
                properties, check_attr_map.get("is_required", {}), is_update=True
            )

            # 取出可编辑属性
            properties = self.get_editable_attr(
                properties, check_attr_map.get("editable", {})
            )
            if not properties:
                return []

        nodes = self.batch_update_node_properties(label, entity_ids, properties)
        return {"data": self.entity_to_list(nodes), "success": True, "message": ""}

    def batch_update_node_properties(
        self, label: str, node_ids: Union[int, List[int]], properties: dict
    ):
        """批量更新节点属性（参数化版本）"""
        validated_label = CQLValidator.validate_label(label) if label else ""
        validated_ids = (
            CQLValidator.validate_ids(node_ids)
            if isinstance(node_ids, list)
            else [CQLValidator.validate_id(node_ids)]
        )

        if not properties:
            raise BaseAppException("properties is empty")

        if self.ENABLE_PARAMETERIZATION:
            # 构建SET子句
            set_parts = []
            params = {"ids": validated_ids}

            for i, (key, value) in enumerate(properties.items()):
                validated_field = CQLValidator.validate_field(key)
                param_name = f"val{i}"
                set_parts.append(f"n.{validated_field} = ${param_name}")
                params[param_name] = value

            label_str = f":{validated_label}" if validated_label else ""
            set_clause = ", ".join(set_parts)
            query = (
                f"MATCH (n{label_str}) WHERE ID(n) IN $ids SET {set_clause} RETURN n"
            )

            nodes = self._execute_query(query, params=params)
        else:
            # 旧逻辑
            label_str = f":{validated_label}" if validated_label else ""
            properties_str = self.format_properties_set(properties)
            nodes = self._execute_query(
                f"MATCH (n{label_str}) WHERE ID(n) IN {validated_ids} SET {properties_str} RETURN n"
            )

        return nodes

    def format_properties_remove(self, attrs: list):
        """格式化properties的remove数据，验证字段名防止注入"""
        properties_str = ""
        for attr in attrs:
            # 验证字段名，防止注入攻击
            validated_attr = CQLValidator.validate_field(attr)
            properties_str += f"n.`{validated_attr}`,"
        return properties_str if properties_str == "" else properties_str[:-1]

    def remove_entitys_properties(self, label: str, params: list, attrs: list):
        """移除某些实体的某些属性（参数化版本）"""

        # 验证标签和属性
        if self.ENABLE_PARAMETERIZATION:
            if label:
                CQLValidator.validate_label(label)
            for attr in attrs:
                CQLValidator.validate_field(attr)

        label_str = f":{label}" if label else ""
        properties_str = self.format_properties_remove(attrs)

        if self.ENABLE_PARAMETERIZATION:
            param_collector = ParameterCollector()
            params_str, query_params = self.format_search_params(
                params, param_collector=param_collector
            )
            params_str = f"WHERE {params_str}" if params_str else ""
            self._execute_query(
                f"MATCH (n{label_str}) {params_str} REMOVE {properties_str} RETURN n",
                params=query_params if query_params else None,
            )
        else:
            params_str, _ = self.format_search_params(params)
            params_str = f"WHERE {params_str}" if params_str else ""
            self._execute_query(
                f"MATCH (n{label_str}) {params_str} REMOVE {properties_str} RETURN n"
            )

    def batch_delete_entity(self, label: str, entity_ids: list):
        """批量删除实体（参数化版本）"""
        validated_label = CQLValidator.validate_label(label) if label else ""
        validated_ids = CQLValidator.validate_ids(entity_ids)

        label_str = f":{validated_label}" if validated_label else ""

        if self.ENABLE_PARAMETERIZATION:
            query = f"MATCH (n{label_str}) WHERE ID(n) IN $ids DETACH DELETE n"
            params = {"ids": validated_ids}
            self._execute_query(query, params=params)
        else:
            self._execute_query(
                f"MATCH (n{label_str}) WHERE ID(n) IN {validated_ids} DETACH DELETE n"
            )

    def detach_delete_entity(self, label: str, id: int):
        """删除实体，以及实体的关联关系（参数化版本）"""
        validated_label = CQLValidator.validate_label(label) if label else ""
        validated_id = CQLValidator.validate_id(id)

        label_str = f":{validated_label}" if validated_label else ""

        if self.ENABLE_PARAMETERIZATION:
            query = f"MATCH (n{label_str}) WHERE ID(n) = $id DETACH DELETE n"
            params = {"id": validated_id}
            self._execute_query(query, params=params)
        else:
            self._execute_query(
                f"MATCH (n{label_str}) WHERE ID(n) = {validated_id} DETACH DELETE n"
            )

    def delete_edge(self, edge_id: int):
        """删除边（参数化版本）"""
        validated_id = CQLValidator.validate_id(edge_id)

        if self.ENABLE_PARAMETERIZATION:
            query = "MATCH ()-[n]->() WHERE ID(n) = $id DELETE n"
            params = {"id": validated_id}
            self._execute_query(query, params=params)
        else:
            self._execute_query(
                f"MATCH ()-[n]->() WHERE ID(n) = {validated_id} DELETE n"
            )

    def entity_objs(self, label: str, params: list, permission_params: str = ""):
        validated_label = CQLValidator.validate_label(label) if label else ""
        label_str = f":{validated_label}" if validated_label else ""

        if self.ENABLE_PARAMETERIZATION:
            param_collector = ParameterCollector()
            params_str, query_params = self.format_search_params(
                params, param_collector=param_collector
            )

            conditions = []
            if params_str:
                conditions.append(params_str)
            if permission_params:
                conditions.append(permission_params)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            sql_str = f"MATCH (n{label_str}) {where_clause} RETURN n"
            inst_objs = self._execute_query(
                sql_str, params=query_params if query_params else None
            )
        else:
            params_str = self.format_final_params(
                params, permission_params=permission_params
            )
            params_str = f"WHERE {params_str}" if params_str else params_str
            sql_str = f"MATCH (n{label_str}) {params_str} RETURN n"
            inst_objs = self._execute_query(sql_str)

        return inst_objs

    def query_topo(self, label: str, inst_id: int):
        """查询实例拓扑（参数化版本）"""

        # 验证参数
        if self.ENABLE_PARAMETERIZATION:
            if label:
                CQLValidator.validate_label(label)
            CQLValidator.validate_id(inst_id)

        label_str = f":{label}" if label else ""

        # 修复 FalkorDB 兼容性问题
        # 查询从指定节点出发的所有路径（作为源节点）
        if self.ENABLE_PARAMETERIZATION:
            src_query = f"MATCH p=(n{label_str})-[*]->(m{label_str}) WHERE ID(n) = $inst_id RETURN p"
            dst_query = f"MATCH p=(m{label_str})-[*]->(n{label_str}) WHERE ID(n) = $inst_id RETURN p"
            query_params = {"inst_id": inst_id}
        else:
            src_query = f"MATCH p=(n{label_str})-[*]->(m{label_str}) WHERE ID(n) = {inst_id} RETURN p"
            dst_query = f"MATCH p=(m{label_str})-[*]->(n{label_str}) WHERE ID(n) = {inst_id} RETURN p"
            query_params = None

        try:
            src_objs = self._execute_query(src_query, params=query_params)
            dst_objs = self._execute_query(dst_query, params=query_params)
        except Exception as e:
            logger.error(f"Query topo failed: {e}")
            # 如果复杂查询失败，使用简单的直接关系查询
            return {}

        return dict(
            src_result=self.format_topo(inst_id, src_objs, True),
            dst_result=self.format_topo(inst_id, dst_objs, False),
        )

    @staticmethod
    def get_topo_config() -> dict:
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            topo_config_path = os.path.join(
                base_dir, "support-files", "topo_config.json"
            )

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
            logger.error(
                "Failed to load topo config: %s, error: %s", topo_config_path, e
            )
            return {}

    def convert_to_cypher_match(
        self, label_str: str, model_id: str, params_str: str, dst: bool = True
    ) -> str:
        edge_type = "dst" if dst else "src"
        default_match = (
            f"MATCH p={f'(m{label_str})-[*]->(n{label_str})' if dst else f'(n{label_str})-[*]->(m{label_str})'} "
            f"WHERE 1=1 {params_str} RETURN p"
        )

        topo_path = self.get_topo_config().get(model_id)

        if not topo_path:
            return default_match

        edge_list = topo_path.get(edge_type)
        if not edge_list:
            return default_match

        cypher_parts = []
        node_aliases = {}
        rep_alias = ""

        for i, relation in enumerate(edge_list):
            self_obj = relation["self_obj"]
            target_obj = relation["target_obj"]
            assoc = relation["assoc"]

            # 验证配置文件中的值，防止配置被篡改导致注入
            validated_self_obj = CQLValidator.validate_field(self_obj)
            validated_target_obj = CQLValidator.validate_field(target_obj)
            validated_assoc = CQLValidator.validate_relation(assoc)

            if self_obj not in node_aliases:
                node_aliases[self_obj] = f"v{i}"
            self_alias = node_aliases[self_obj]

            if i == 0:
                if edge_type == "src":
                    rep_alias = self_alias
                cypher_parts.append(
                    f"({self_alias}:instance {{model_id: '{validated_self_obj}'}})"
                )

            if target_obj not in node_aliases:
                node_aliases[target_obj] = f"v{i + 1}"
            target_alias = node_aliases[target_obj]
            if edge_type == "dst":
                rep_alias = target_alias
            cypher_parts.append(
                f"-[:{validated_assoc}]->({target_alias}:instance {{model_id: '{validated_target_obj}'}})"
            )

        match_path = "".join(cypher_parts)
        where_clause = f"WHERE 1=1 {params_str.replace('n', rep_alias)}"

        return f"MATCH p={match_path}\n{where_clause}\nRETURN p"

    def query_topo_test_config(self, label: str, inst_id: int, model_id: str):
        """查询实例拓扑（参数化版本）"""

        # 验证参数
        if self.ENABLE_PARAMETERIZATION:
            if label:
                CQLValidator.validate_label(label)
            CQLValidator.validate_id(inst_id)
            CQLValidator.validate_field(model_id)  # 验证 model_id 格式

        label_str = f":{label}" if label else ""

        # 构建参数化查询
        if self.ENABLE_PARAMETERIZATION:
            query_params = {"inst_id": inst_id}
            params_str = f"AND ID(n) = $inst_id"
        else:
            params_str, _ = self.format_search_params(
                [{"field": "id", "type": "id=", "value": inst_id}]
            )
            if params_str:
                params_str = f"AND {params_str}"
            query_params = None

        src_query = self.convert_to_cypher_match(
            label_str, model_id, params_str, dst=False
        )
        dst_query = self.convert_to_cypher_match(
            label_str, model_id, params_str, dst=True
        )

        src_objs = self._execute_query(src_query, params=query_params)
        dst_objs = self._execute_query(dst_query, params=query_params)

        return dict(
            src_result=self.format_topo(inst_id, src_objs, True),
            dst_result=self.format_topo(inst_id, dst_objs, False),
        )

    def query_topo_lite(
        self, label: str, inst_id: int, depth: int = 3, exclude_ids=None
    ):
        """查询实例拓扑：限制返回层级，减少前端一次性渲染与网络传输压力"""

        depth = max(1, int(depth))
        probe_depth = depth + 1

        if self.ENABLE_PARAMETERIZATION:
            if label:
                CQLValidator.validate_label(label)
            CQLValidator.validate_id(inst_id)

        label_str = f":{label}" if label else ""

        if self.ENABLE_PARAMETERIZATION:
            query_params = {"inst_id": inst_id}
            src_query = (
                f"MATCH p=(n{label_str})-[*1..{probe_depth}]->(m{label_str}) "
                "WHERE ID(n) = $inst_id RETURN p"
            )
            dst_query = (
                f"MATCH p=(m{label_str})-[*1..{probe_depth}]->(n{label_str}) "
                "WHERE ID(n) = $inst_id RETURN p"
            )
        else:
            query_params = None
            src_query = (
                f"MATCH p=(n{label_str})-[*1..{probe_depth}]->(m{label_str}) "
                f"WHERE ID(n) = {inst_id} RETURN p"
            )
            dst_query = (
                f"MATCH p=(m{label_str})-[*1..{probe_depth}]->(n{label_str}) "
                f"WHERE ID(n) = {inst_id} RETURN p"
            )

        src_objs = self._execute_query(src_query, params=query_params)
        dst_objs = self._execute_query(dst_query, params=query_params)

        return dict(
            src_result=self.format_topo_lite(
                inst_id, src_objs, True, depth=depth, exclude_ids=exclude_ids
            ),
            dst_result=self.format_topo_lite(
                inst_id, dst_objs, False, depth=depth, exclude_ids=exclude_ids
            ),
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
                    props = {k: v for k, v in node.properties.items() if k != "_id"}
                    entity_map[node.id] = dict(_id=node.id, _label=node.labels[0], **props)
                for relationship in relationships:
                    props = {k: v for k, v in relationship.properties.items() if k != "_id"}
                    edge_map[relationship.id] = dict(
                        _id=relationship.id,
                        _label=relationship.relation,
                        **props,
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
            "model_id": entity.get("model_id"),
            "inst_name": entity.get("inst_name"),
            "children": [],
        }

        if entity_is_src:
            entity_key, child_entity_key = "src", "dst"
        else:
            entity_key, child_entity_key = "dst", "src"

        for edge in edges:
            if edge[f"{entity_key}_inst_id"] == entity["_id"]:
                child_entity = self.find_entity_by_id(
                    edge[f"{child_entity_key}_inst_id"], entities
                )
                if child_entity:
                    child_node = self.create_node(
                        child_entity, edges, entities, entity_is_src
                    )
                    child_node["model_asst_id"] = edge["model_asst_id"]
                    child_node["asst_id"] = edge["asst_id"]
                    node["children"].append(child_node)
        return node

    def format_topo_lite(
        self, start_id, objs, entity_is_src=True, depth: int = 3, exclude_ids=None
    ):
        """格式化拓扑数据：限制层级并支持排除父节点集合"""

        all_results = objs.result_set

        exclude_id_set = set()
        for value in exclude_ids or []:
            try:
                exclude_id_set.add(int(value))
            except (TypeError, ValueError):
                continue
        exclude_id_set.discard(start_id)

        edge_map = {}
        entity_map = {}

        for obj in all_results:
            for element in obj:
                nodes = getattr(element, "_nodes", [])
                relationships = getattr(element, "_edges", [])
                for node in nodes:
                    props = {k: v for k, v in node.properties.items() if k != "_id"}
                    entity_map[node.id] = dict(_id=node.id, _label=node.labels[0], **props)
                for relationship in relationships:
                    props = {k: v for k, v in relationship.properties.items() if k != "_id"}
                    edge_map[relationship.id] = dict(
                        _id=relationship.id,
                        _label=relationship.relation,
                        **props,
                    )

        edges = list(edge_map.values())
        edges = [
            edge
            for edge in edges
            if edge.get("src_inst_id") != edge.get("dst_inst_id")
        ]

        if exclude_id_set:
            for node_id in exclude_id_set:
                entity_map.pop(node_id, None)
            edges = [
                edge
                for edge in edges
                if edge.get("src_inst_id") not in exclude_id_set
                and edge.get("dst_inst_id") not in exclude_id_set
            ]

        entities = list(entity_map.values())
        if start_id not in entity_map:
            return {}

        return self.create_node_lite(
            entity_map[start_id],
            edges,
            entities,
            entity_is_src,
            level=1,
            max_depth=max(1, int(depth)),
        )

    def create_node_lite(
        self,
        entity,
        edges,
        entities,
        entity_is_src=True,
        level: int = 1,
        max_depth: int = 3,
    ):
        node = {
            "_id": entity.get("_id"),
            "model_id": entity.get("model_id"),
            "inst_name": entity.get("inst_name")
            or entity.get("ip_addr")
            or str(entity.get("_id")),
            "children": [],
        }

        if entity_is_src:
            entity_key, child_entity_key = "src", "dst"
        else:
            entity_key, child_entity_key = "dst", "src"

        if level >= max_depth:
            node["has_more"] = any(
                edge.get(f"{entity_key}_inst_id") == entity.get("_id")
                for edge in edges
            )
            return node

        for edge in edges:
            if edge.get(f"{entity_key}_inst_id") == entity.get("_id"):
                child_entity = self.find_entity_by_id(
                    edge.get(f"{child_entity_key}_inst_id"), entities
                )
                if child_entity:
                    child_node = self.create_node_lite(
                        child_entity,
                        edges,
                        entities,
                        entity_is_src,
                        level=level + 1,
                        max_depth=max_depth,
                    )
                    child_node["model_asst_id"] = edge.get("model_asst_id")
                    child_node["asst_id"] = edge.get("asst_id")
                    node["children"].append(child_node)
        return node

    def find_entity_by_id(self, entity_id, entities):
        """根据ID找实体"""
        for entity in entities:
            if entity["_id"] == entity_id:
                return entity
        return None

    def entity_count(
        self, label: str, group_by_attr: str, format_permission_dict: dict
    ):
        """
        按指定字段分组统计实体数量（参数化版本）

        Args:
            label: 实体标签
            group_by_attr: 分组字段
            format_permission_dict: 权限过滤字典 {organization_id: query_list}

        Returns:
            {group_value: count} 统计字典
        """
        # 验证标签和字段名
        if self.ENABLE_PARAMETERIZATION and label:
            CQLValidator.validate_label(label)
        if self.ENABLE_PARAMETERIZATION:
            CQLValidator.validate_field(group_by_attr)

        label_str = f":{label}" if label else ""

        # 参数收集器
        param_collector = ParameterCollector() if self.ENABLE_PARAMETERIZATION else None

        # 构建权限参数 这里的参数是在基础参数基础上做AND 查询的 每个for的数据之间的关系是OR的关系
        permission_filters = []
        for organization_id, query_list in format_permission_dict.items():
            organization_query = [
                {"field": "organization", "type": "list[]", "value": [organization_id]}
            ]

            if self.ENABLE_PARAMETERIZATION:
                base_permission_str, base_params = self.format_search_params(
                    organization_query,
                    param_type="AND",
                    param_collector=param_collector,
                )
                org_permission_str, org_params = self.format_search_params(
                    query_list, param_type="OR", param_collector=param_collector
                )
            else:
                base_permission_str, _ = self.format_search_params(
                    organization_query, param_type="AND"
                )
                org_permission_str, _ = self.format_search_params(
                    query_list, param_type="OR"
                )

            if base_permission_str and org_permission_str:
                # org_permission_str 已经有括号，只需要外层括号保证 AND 优先级
                combined_filter = f"({base_permission_str} AND {org_permission_str})"
                permission_filters.append(combined_filter)
            elif base_permission_str:
                # 只有组织条件，直接使用（format_search_params 返回的已有括号）
                permission_filters.append(base_permission_str)

        # 组合最终查询条件：基础参数 AND (权限条件1 OR 权限条件2 OR ...)
        final_conditions = []
        if permission_filters:
            # 多个组织的权限条件用 OR 连接
            if len(permission_filters) == 1:
                final_conditions.append(permission_filters[0])
            else:
                permission_str = " OR ".join(permission_filters)
                final_conditions.append(f"({permission_str})")

        filter_str = " AND ".join(final_conditions) if final_conditions else ""
        if filter_str:
            filter_str = f"WHERE {filter_str}"

        count_sql = f"MATCH (n{label_str}) {filter_str} RETURN n.{group_by_attr} AS {group_by_attr}, COUNT(n) AS count"

        query_params = param_collector.params if self.ENABLE_PARAMETERIZATION else None

        # 调试日志：打印 entity_count 的查询
        logger.debug(f"[entity_count] SQL: {count_sql}")
        logger.debug(f"[entity_count] Params: {query_params}")
        logger.debug(f"[entity_count] format_permission_dict: {format_permission_dict}")

        data = self._execute_query(count_sql, params=query_params)
        result = FormatDBResult(data).to_result_of_count()
        return result

    def full_text_stats(
        self,
        search: str,
        permission_params: str = "",
        inst_name_params: str = "",
        created: str = "",
        case_sensitive: bool = False,
        permission_params_dict: dict = None,
    ) -> dict:
        """
        全文检索 - 模型统计接口（参数化版本）
        返回搜索结果中每个模型的总数统计

        Args:
            search: 搜索关键词
            permission_params: 权限过滤参数（与现有全文检索保持一致）
            inst_name_params: 实例名称过滤参数
            created: 创建者过滤
            case_sensitive: 是否区分大小写（True=精准匹配，False=模糊匹配，默认False）
            permission_params_dict: 权限参数字典（参数化模式下使用）

        Returns:
            {
                "total": 156,  # 所有匹配实例总数
                "model_stats": [
                    {"model_id": "Center", "count": 45},
                    {"model_id": "阿里云", "count": 23}
                ]
            }
        """
        logger.info(
            f"[全文检索统计] 开始查询，关键词: {search}, 区分大小写: {case_sensitive}"
        )

        # 获取排除字段
        exclude_fields = ExcludeFieldsCache.get_exclude_fields()
        if not exclude_fields:
            raise BaseAppException("排除字段缓存未初始化")

        # 参数化查询参数（合并权限参数）
        query_params = permission_params_dict.copy() if permission_params_dict else {}
        conditions = []

        # 权限和实例名称过滤（保持原逻辑）
        or_filters = []
        if permission_params:
            or_filters.append(permission_params)
        if inst_name_params:
            or_filters.append(inst_name_params)
        if or_filters:
            or_condition = " OR ".join(or_filters)
            conditions.append(f"({or_condition})")

        # 创建者过滤
        if created:
            if self.ENABLE_PARAMETERIZATION:
                param_name = "created_by"
                query_params[param_name] = created
                conditions.append(f"n._creator = ${param_name}")
            else:
                validated_created = self.escape_cql_string(created)
                conditions.append(f"n._creator = '{validated_created}'")

        # 全文检索条件
        exclude_list_str = self._build_exclude_fields_list(exclude_fields)

        if self.ENABLE_PARAMETERIZATION:
            query_params["search_term"] = search

            if case_sensitive:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toString(n[key]) CONTAINS $search_term)"
                )
            else:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toLower(toString(n[key])) CONTAINS toLower($search_term))"
                )
        else:
            escaped_search = self.escape_cql_string(search)

            if case_sensitive:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toString(n[key]) CONTAINS '{escaped_search}')"
                )
            else:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toLower(toString(n[key])) CONTAINS toLower('{escaped_search}'))"
                )

        conditions.append(search_condition)

        where_clause = " AND ".join(conditions) if conditions else "true"

        # 执行统计查询
        query = (
            f"MATCH (n:{INSTANCE}) "
            f"WHERE {where_clause} "
            f"RETURN n.model_id AS model_id, COUNT(n) AS count "
            f"ORDER BY count DESC"
        )

        result = self._execute_query(
            query, params=query_params if self.ENABLE_PARAMETERIZATION else None
        )
        formatted_result = FormatDBResult(result).to_result_of_count()

        # 构建返回结果
        model_stats = []
        total = 0
        for model_id, count in formatted_result.items():
            model_stats.append({"model_id": model_id, "count": count})
            total += count

        logger.info(
            f"[全文检索统计] 查询成功，总数: {total}, 模型数: {len(model_stats)}"
        )

        return {"total": total, "model_stats": model_stats}

    def full_text_by_model(
        self,
        search: str,
        model_id: str,
        permission_params: str = "",
        inst_name_params: str = "",
        created: str = "",
        page: int = 1,
        page_size: int = 10,
        case_sensitive: bool = False,
        permission_params_dict: dict = None,
    ) -> dict:
        """
        全文检索 - 模型数据查询接口
        返回指定模型的分页数据

        Args:
            search: 搜索关键词
            model_id: 目标模型ID（必填）
            permission_params: 权限过滤参数（与现有全文检索保持一致）
            inst_name_params: 实例名称过滤参数
            created: 创建者过滤
            page: 页码（从1开始）
            page_size: 每页大小（默认10）
            case_sensitive: 是否区分大小写（True=精准匹配，False=模糊匹配，默认False）
            permission_params_dict: 权限参数字典（参数化模式下使用）

        Returns:
            {
                "model_id": "Center",
                "total": 45,  # 该模型匹配的总数
                "page": 1,
                "page_size": 10,
                "data": [{...}, {...}]  # 分页数据
            }
        """
        logger.info(
            f"[全文检索数据] 开始查询，关键词: {search}, 模型: {model_id}, "
            f"页码: {page}, 每页: {page_size}, 区分大小写: {case_sensitive}"
        )

        # 参数校验
        if not model_id:
            raise BaseAppException("model_id is required")

        if page < 1:
            raise BaseAppException("page must be >= 1")

        if page_size < 1 or page_size > 100:
            raise BaseAppException("page_size must be between 1 and 100")

        # 获取排除字段
        exclude_fields = ExcludeFieldsCache.get_exclude_fields()
        if not exclude_fields:
            raise BaseAppException("排除字段缓存未初始化")

        # 参数化查询参数（合并权限参数）
        query_params = permission_params_dict.copy() if permission_params_dict else {}
        conditions = []

        # 权限和实例名称过滤
        or_filters = []
        if permission_params:
            or_filters.append(permission_params)
        if inst_name_params:
            or_filters.append(inst_name_params)
        if or_filters:
            or_condition = " OR ".join(or_filters)
            conditions.append(f"({or_condition})")

        # 创建者过滤
        if created:
            if self.ENABLE_PARAMETERIZATION:
                query_params["created_by"] = created
                conditions.append(f"n._creator = $created_by")
            else:
                validated_created = self.escape_cql_string(created)
                conditions.append(f"n._creator = '{validated_created}'")

        # 模型ID过滤
        if self.ENABLE_PARAMETERIZATION:
            CQLValidator.validate_field(model_id)  # 验证模型ID格式
            query_params["model_id"] = model_id
            conditions.append(f"n.model_id = $model_id")
        else:
            escaped_model_id = self.escape_cql_string(model_id)
            conditions.append(f"n.model_id = '{escaped_model_id}'")

        # 全文检索条件
        exclude_list_str = self._build_exclude_fields_list(exclude_fields)

        if self.ENABLE_PARAMETERIZATION:
            query_params["search_term"] = search

            if case_sensitive:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toString(n[key]) CONTAINS $search_term)"
                )
            else:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toLower(toString(n[key])) CONTAINS toLower($search_term))"
                )
        else:
            escaped_search = self.escape_cql_string(search)

            if case_sensitive:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toString(n[key]) CONTAINS '{escaped_search}')"
                )
            else:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toLower(toString(n[key])) CONTAINS toLower('{escaped_search}'))"
                )

        conditions.append(search_condition)
        where_clause = " AND ".join(conditions) if conditions else "true"

        # 第一步：查询该模型的总数
        count_query = (
            f"MATCH (n:{INSTANCE}) WHERE {where_clause} RETURN COUNT(n) AS total"
        )

        count_result = self._execute_query(
            count_query, params=query_params if self.ENABLE_PARAMETERIZATION else None
        )
        count_data = FormatDBResult(count_result).to_list_of_lists()
        total = count_data[0] if count_data else 0

        logger.debug(f"[全文检索数据] 模型 {model_id} 总数: {total}")

        # 第二步：查询分页数据
        skip = (page - 1) * page_size
        data_query = (
            f"MATCH (n:{INSTANCE}) "
            f"WHERE {where_clause} "
            f"RETURN n "
            f"ORDER BY ID(n) "
            f"SKIP {skip} LIMIT {page_size}"
        )

        data_result = self._execute_query(
            data_query, params=query_params if self.ENABLE_PARAMETERIZATION else None
        )
        data = self.entity_to_list(data_result)

        logger.info(
            f"[全文检索数据] 查询成功，模型: {model_id}, 总数: {total}, "
            f"返回: {len(data)} 条数据"
        )

        return {
            "model_id": model_id,
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": data,
        }

    def full_text(
        self,
        search: str,
        permission_params: str = "",
        inst_name_params: str = "",
        created: str = "",
        case_sensitive: bool = False,
    ):
        """
        全文检索（兼容旧接口，参数化版本）
        推荐使用 full_text_stats 和 full_text_by_model 替代

        Args:
            search: 搜索关键词
            permission_params: 权限过滤参数
            inst_name_params: 实例名称过滤参数
            created: 创建者过滤
            case_sensitive: 是否区分大小写（默认False，模糊匹配）

        Returns:
            匹配的实例列表
        """
        logger.info(f"[全文检索] 开始查询（旧接口），关键词: {search}")

        # 获取排除字段
        exclude_fields = ExcludeFieldsCache.get_exclude_fields()
        if not exclude_fields:
            raise BaseAppException("排除字段缓存未初始化")

        # 参数化查询参数
        query_params = {}
        conditions = []

        # 权限和实例名称过滤
        or_filters = []
        if permission_params:
            or_filters.append(permission_params)
        if inst_name_params:
            or_filters.append(inst_name_params)
        if or_filters:
            or_condition = " OR ".join(or_filters)
            conditions.append(f"({or_condition})")

        # 创建者过滤
        if created:
            if self.ENABLE_PARAMETERIZATION:
                query_params["created_by"] = created
                conditions.append(f"n._creator = $created_by")
            else:
                validated_created = self.escape_cql_string(created)
                conditions.append(f"n._creator = '{validated_created}'")

        # 全文检索条件
        exclude_list_str = self._build_exclude_fields_list(exclude_fields)

        if self.ENABLE_PARAMETERIZATION:
            query_params["search_term"] = search

            if case_sensitive:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toString(n[key]) CONTAINS $search_term)"
                )
            else:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toLower(toString(n[key])) CONTAINS toLower($search_term))"
                )
        else:
            escaped_search = self.escape_cql_string(search)

            if case_sensitive:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toString(n[key]) CONTAINS '{escaped_search}')"
                )
            else:
                search_condition = (
                    f"ANY(key IN keys(n) WHERE "
                    f"none(excluded IN {exclude_list_str} WHERE excluded = key) AND "
                    f"n[key] IS NOT NULL AND "
                    f"toLower(toString(n[key])) CONTAINS toLower('{escaped_search}'))"
                )

        conditions.append(search_condition)
        where_clause = " AND ".join(conditions) if conditions else "true"

        query = f"MATCH (n:{INSTANCE}) WHERE {where_clause} RETURN n"

        objs = self._execute_query(
            query, params=query_params if self.ENABLE_PARAMETERIZATION else None
        )
        result = self.entity_to_list(objs)

        logger.info(f"[全文检索] 查询成功，返回: {len(result)} 条数据")
        return result

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
                properties_key = tuple(
                    [properties.get(k) for k in unique_key if k in properties]
                )
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
                        results = self.batch_update_entity_properties(
                            label=label,
                            entity_ids=[node.get("_id")],
                            properties=properties,
                            check_attr_map=check_attr_map,
                        )
                        results["data"] = results["data"][0]
                        update_results.append(results)
                    except Exception as e:
                        logger.info(f"update entity error: {e}")
                        update_results.append(
                            {
                                "success": False,
                                "data": properties,
                                "message": "update entity error",
                            }
                        )

                else:
                    # 暂存统一新增
                    add_nodes.append(properties)
        else:
            add_nodes = properties_list
        add_results = self.batch_create_entity(
            label=label,
            properties_list=add_nodes,
            check_attr_map=check_attr_map,
            exist_items=exist_items,
            operator=operator,
        )
        return add_results, update_results
