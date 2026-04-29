# -- coding: utf-8 --
"""
YAML序列化与反序列化工具

负责将数据库对象转换为YAML格式，以及解析YAML内容。
敏感字段脱敏处理在此模块统一执行。
"""

from datetime import datetime
from typing import Any, Optional

import yaml

from apps.operation_analysis.constants.import_export import (
    SENSITIVE_FIELDS,
    SENSITIVE_PLACEHOLDER,
    YAML_SCHEMA_VERSION,
    BUSINESS_KEY_SEPARATOR,
    ObjectType,
)
from apps.operation_analysis.services.import_export.view_sets import (
    normalize_canvas_view_sets_for_yaml,
    rewrite_canvas_view_sets_refs_for_yaml,
)


class YAMLSerializer:
    """
    YAML序列化器

    提供数据库对象到YAML的转换能力，包含敏感字段脱敏处理。
    """

    @staticmethod
    def generate_namespace_key(name: str) -> str:
        """
        生成命名空间业务键

        规则：namespace_key = namespace.name
        """
        return name

    @staticmethod
    def generate_datasource_key(name: str, rest_api: str) -> str:
        """
        生成数据源业务键

        规则：datasource_key = datasource.name + "::" + datasource.rest_api
        """
        return f"{name}{BUSINESS_KEY_SEPARATOR}{rest_api}"

    @staticmethod
    def generate_canvas_key(object_type: str, name: str) -> str:
        """
        生成画布对象业务键

        规则：
        - dashboard_key = "dashboard::" + dashboard.name
        - topology_key = "topology::" + topology.name
        - architecture_key = "architecture::" + architecture.name
        """
        return f"{object_type}{BUSINESS_KEY_SEPARATOR}{name}"

    @staticmethod
    def mask_sensitive_fields(data: dict) -> dict:
        """
        脱敏处理字典中的敏感字段

        递归扫描字典，将匹配SENSITIVE_FIELDS的字段值替换为占位符。
        """
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            if key.lower() in SENSITIVE_FIELDS:
                result[key] = SENSITIVE_PLACEHOLDER
            elif isinstance(value, dict):
                result[key] = YAMLSerializer.mask_sensitive_fields(value)
            elif isinstance(value, list):
                result[key] = [YAMLSerializer.mask_sensitive_fields(item) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        return result

    @staticmethod
    def namespace_to_dict(namespace) -> dict:
        """
        将NameSpace模型实例转换为YAML字典结构

        敏感字段（password）统一脱敏为占位符。
        """
        return {
            "key": YAMLSerializer.generate_namespace_key(namespace.name),
            "name": namespace.name,
            "domain": namespace.domain,
            "namespace": namespace.namespace,
            "account": namespace.account,
            "password": SENSITIVE_PLACEHOLDER,
            "enable_tls": namespace.enable_tls,
            "desc": namespace.desc or "",
        }

    @staticmethod
    def datasource_to_dict(datasource, namespace_keys: list[str] = None) -> dict:
        """
        将DataSourceAPIModel实例转换为YAML字典结构

        params字段中的敏感信息会被脱敏处理。
        """
        raw_params = datasource.params if isinstance(datasource.params, (list, dict)) else []
        if isinstance(raw_params, list):
            masked_params = [YAMLSerializer.mask_sensitive_fields(item) if isinstance(item, dict) else item for item in raw_params]
        else:
            masked_params = YAMLSerializer.mask_sensitive_fields(raw_params)

        tag_names = [tag.name for tag in datasource.tag.all()]

        if namespace_keys is None:
            namespace_keys = [ns.name for ns in datasource.namespaces.all()]

        return {
            "key": YAMLSerializer.generate_datasource_key(datasource.name, datasource.rest_api),
            "name": datasource.name,
            "rest_api": datasource.rest_api,
            "desc": datasource.desc or "",
            "is_active": datasource.is_active,
            "params": masked_params,
            "tags": tag_names,
            "chart_type": datasource.chart_type or [],
            "field_schema": datasource.field_schema or [],
            "namespace_keys": namespace_keys,
        }

    @staticmethod
    def dashboard_to_dict(dashboard, datasource_keys: list[str] = None, namespace_keys: list[str] = None) -> dict:
        """
        将Dashboard实例转换为YAML字典结构
        """
        return {
            "key": YAMLSerializer.generate_canvas_key(ObjectType.DASHBOARD.value, dashboard.name),
            "name": dashboard.name,
            "desc": dashboard.desc or "",
            "filters": dashboard.filters or [],
            "other": dashboard.other or {},
            "view_sets": rewrite_canvas_view_sets_refs_for_yaml(
                normalize_canvas_view_sets_for_yaml(dashboard.view_sets or [], ObjectType.DASHBOARD),
                ObjectType.DASHBOARD,
                {},
            ),
            "refs": {
                "datasource_keys": datasource_keys or [],
                "namespace_keys": namespace_keys or [],
            },
        }

    @staticmethod
    def topology_to_dict(topology, datasource_keys: list[str] = None, namespace_keys: list[str] = None) -> dict:
        """
        将Topology实例转换为YAML字典结构
        """
        return {
            "key": YAMLSerializer.generate_canvas_key(ObjectType.TOPOLOGY.value, topology.name),
            "name": topology.name,
            "desc": topology.desc or "",
            "other": topology.other or {},
            "view_sets": rewrite_canvas_view_sets_refs_for_yaml(
                normalize_canvas_view_sets_for_yaml(topology.view_sets or [], ObjectType.TOPOLOGY),
                ObjectType.TOPOLOGY,
                {},
            ),
            "refs": {
                "datasource_keys": datasource_keys or [],
                "namespace_keys": namespace_keys or [],
            },
        }

    @staticmethod
    def architecture_to_dict(architecture, datasource_keys: list[str] = None, namespace_keys: list[str] = None) -> dict:
        """
        将Architecture实例转换为YAML字典结构
        """
        return {
            "key": YAMLSerializer.generate_canvas_key(ObjectType.ARCHITECTURE.value, architecture.name),
            "name": architecture.name,
            "desc": architecture.desc or "",
            "other": architecture.other or {},
            "view_sets": rewrite_canvas_view_sets_refs_for_yaml(
                normalize_canvas_view_sets_for_yaml(architecture.view_sets or [], ObjectType.ARCHITECTURE),
                ObjectType.ARCHITECTURE,
                {},
            ),
            "refs": {
                "datasource_keys": datasource_keys or [],
                "namespace_keys": namespace_keys or [],
            },
        }

    @staticmethod
    def build_yaml_document(
        dashboards: list = None,
        topologies: list = None,
        architectures: list = None,
        datasources: list = None,
        namespaces: list = None,
        organization_id: int = 0,
    ) -> dict:
        """
        构建完整的YAML文档结构

        包含meta元数据和各对象章节。
        """
        dashboards = dashboards or []
        topologies = topologies or []
        architectures = architectures or []
        datasources = datasources or []
        namespaces = namespaces or []

        return {
            "meta": {
                "schema_version": YAML_SCHEMA_VERSION,
                "exported_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": {
                    "organization_id": organization_id,
                },
                "object_counts": {
                    "dashboards": len(dashboards),
                    "topologies": len(topologies),
                    "architectures": len(architectures),
                    "datasources": len(datasources),
                    "namespaces": len(namespaces),
                },
            },
            "dashboards": dashboards,
            "topologies": topologies,
            "architectures": architectures,
            "datasources": datasources,
            "namespaces": namespaces,
        }

    @staticmethod
    def to_yaml_string(document: dict) -> str:
        """
        将字典转换为YAML字符串

        使用稳定排序确保相同配置重复导出时内容一致。
        """
        return yaml.dump(
            document,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
        )

    @staticmethod
    def parse_yaml(yaml_content: str) -> dict:
        """
        解析YAML字符串为字典

        使用safe_load确保安全性。
        """
        return yaml.safe_load(yaml_content) or {}
