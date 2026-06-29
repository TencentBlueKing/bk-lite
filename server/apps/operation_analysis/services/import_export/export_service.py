# -- coding: utf-8 --
"""
YAML导出服务

负责将画布对象和配置对象导出为统一YAML格式。
包含：依赖收敛、敏感字段脱敏、稳定排序、YAML序列化等功能。
"""

from datetime import datetime, timezone
from typing import Any

import yaml

from apps.operation_analysis.constants.import_export import (
    BUSINESS_KEY_SEPARATOR,
    CANVAS_TYPES,
    OBJECT_TYPE_TO_SECTION,
    SENSITIVE_FIELDS,
    SENSITIVE_PLACEHOLDER,
    YAML_SCHEMA_VERSION,
    ObjectType,
    ScopeType,
)
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.models.models import Architecture, Dashboard, Report, Screen, Topology
from apps.operation_analysis.services.import_export.view_sets import (
    normalize_canvas_view_sets_for_storage,
    normalize_canvas_view_sets_for_yaml,
    rewrite_canvas_view_sets_refs_for_yaml,
)


class ExportService:
    """
    YAML导出服务

    遵循Tech Plan 5.1节导出流程：
    1. 校验入参
    2. 读取对象
    3. 依赖收敛（仅收集实际引用）
    4. DB对象 -> YAML对象转换
    5. 敏感字段脱敏
    6. 稳定排序
    7. 序列化输出
    8. 返回summary
    """

    MODEL_MAP = {
        ObjectType.DASHBOARD: Dashboard,
        ObjectType.TOPOLOGY: Topology,
        ObjectType.ARCHITECTURE: Architecture,
        ObjectType.SCREEN: Screen,
        ObjectType.REPORT: Report,
        ObjectType.DATASOURCE: DataSourceAPIModel,
        ObjectType.NAMESPACE: NameSpace,
    }

    @staticmethod
    def generate_business_key(obj: Any, object_type: ObjectType) -> str:
        """
        根据对象类型生成业务键

        业务键规则（Tech Plan 3.2节）：
        - namespace_key = namespace.name
        - datasource_key = name + "::" + rest_api
        - canvas_key = "type::" + name
        """
        if object_type == ObjectType.NAMESPACE:
            return obj.name
        elif object_type == ObjectType.DATASOURCE:
            return f"{obj.name}{BUSINESS_KEY_SEPARATOR}{obj.rest_api}"
        else:
            return f"{object_type.value}{BUSINESS_KEY_SEPARATOR}{obj.name}"

    @staticmethod
    def mask_sensitive_fields(data: dict) -> dict:
        """
        对敏感字段进行脱敏处理

        遍历字典，将SENSITIVE_FIELDS中定义的字段值替换为占位符。
        """
        result = {}
        for key, value in data.items():
            if key in SENSITIVE_FIELDS and value:
                result[key] = SENSITIVE_PLACEHOLDER
            elif isinstance(value, dict):
                result[key] = ExportService.mask_sensitive_fields(value)
            elif isinstance(value, list):
                result[key] = [ExportService.mask_sensitive_fields(item) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        return result

    @staticmethod
    def convert_namespace_to_yaml(ns: NameSpace) -> dict:
        """将命名空间对象转换为YAML结构"""
        return ExportService.mask_sensitive_fields(
            {
                "key": ExportService.generate_business_key(ns, ObjectType.NAMESPACE),
                "name": ns.name,
                "domain": ns.domain,
                "namespace": ns.namespace,
                "account": ns.account,
                "password": ns.password,
                "enable_tls": ns.enable_tls,
                "desc": ns.desc or "",
            }
        )

    @staticmethod
    def convert_datasource_to_yaml(ds: DataSourceAPIModel) -> dict:
        """将数据源对象转换为YAML结构"""
        namespace_keys = [ns.name for ns in ds.namespaces.all()]
        tag_names = [tag.name for tag in ds.tag.all()]

        return ExportService.mask_sensitive_fields(
            {
                "key": ExportService.generate_business_key(ds, ObjectType.DATASOURCE),
                "name": ds.name,
                "rest_api": ds.rest_api,
                "desc": ds.desc or "",
                # [内部预留] is_active 字段仅内部使用，无产品功能依赖
                "is_active": ds.is_active,
                "params": ds.params or [],
                "tags": tag_names,
                "chart_type": ds.chart_type or [],
                "field_schema": ds.field_schema or [],
                "namespace_keys": namespace_keys,
            }
        )

    @staticmethod
    def extract_canvas_dependencies(view_sets: list | dict, object_type: ObjectType) -> tuple[set, set]:
        """
        从画布的view_sets中提取依赖的数据源和命名空间

        依赖收敛规则：遍历view_sets中的组件配置，提取实际引用的数据源ID和命名空间ID。
        返回：(datasource_ids, namespace_ids)
        """
        datasource_ids = set()
        namespace_ids = set()

        if not view_sets:
            return datasource_ids, namespace_ids

        normalized = normalize_canvas_view_sets_for_storage(view_sets, object_type)

        def collect_datasource_ids(value: Any):
            if isinstance(value, list):
                for item in value:
                    collect_datasource_ids(item)
                return

            if not isinstance(value, dict):
                return

            value_config = value.get("valueConfig")
            if isinstance(value_config, dict):
                ds_id = value_config.get("dataSource")
                if isinstance(ds_id, int):
                    datasource_ids.add(ds_id)

            for nested in value.values():
                collect_datasource_ids(nested)

        if object_type in CANVAS_TYPES:
            collect_datasource_ids(normalized)

        return datasource_ids, namespace_ids

    @staticmethod
    def convert_canvas_to_yaml(canvas: Any, object_type: ObjectType, ds_key_map: dict, ns_key_map: dict) -> dict:
        """
        将画布对象（仪表盘/拓扑/架构图）转换为YAML结构

        ds_key_map: {datasource_id: datasource_key} 映射
        ns_key_map: {namespace_id: namespace_key} 映射
        """
        raw_view_sets = canvas.view_sets or []
        ds_ids, ns_ids = ExportService.extract_canvas_dependencies(raw_view_sets, object_type)
        view_sets = rewrite_canvas_view_sets_refs_for_yaml(
            normalize_canvas_view_sets_for_yaml(raw_view_sets, object_type),
            object_type,
            ds_key_map,
        )

        datasource_keys = [ds_key_map[ds_id] for ds_id in ds_ids if ds_id in ds_key_map]
        namespace_keys = [ns_key_map[ns_id] for ns_id in ns_ids if ns_id in ns_key_map]

        base_data = {
            "key": ExportService.generate_business_key(canvas, object_type),
            "name": canvas.name,
            "desc": canvas.desc or "",
            "other": canvas.other or {},
            "view_sets": view_sets,
            "refs": {
                "datasource_keys": datasource_keys,
                "namespace_keys": namespace_keys,
            },
        }

        # Dashboard有额外的filters字段
        if object_type == ObjectType.DASHBOARD and hasattr(canvas, "filters"):
            base_data["filters"] = canvas.filters or []

        return base_data

    @classmethod
    def _collect_canvas_dependencies(cls, object_type: str, object_ids: list[int]) -> tuple[set, set]:
        collected_datasource_ids = set()
        collected_namespace_ids = set()

        if object_type not in [t.value for t in CANVAS_TYPES]:
            return collected_datasource_ids, collected_namespace_ids

        ot = ObjectType(object_type)
        model = cls.MODEL_MAP[ot]

        for canvas in model.objects.filter(id__in=object_ids):
            ds_ids, ns_ids = cls.extract_canvas_dependencies(canvas.view_sets or [], ot)
            collected_datasource_ids.update(ds_ids)
            collected_namespace_ids.update(ns_ids)

        return collected_datasource_ids, collected_namespace_ids

    @classmethod
    def _collect_config_objects(cls, object_type: str, object_ids: list[int]) -> tuple[set, set]:
        if object_type == ObjectType.DATASOURCE.value:
            existing = set(DataSourceAPIModel.objects.filter(id__in=object_ids).values_list("id", flat=True))
            return existing, set()
        elif object_type == ObjectType.NAMESPACE.value:
            existing = set(NameSpace.objects.filter(id__in=object_ids).values_list("id", flat=True))
            return set(), existing
        return set(), set()

    @classmethod
    def _convert_canvases_to_yaml(
        cls, scope_type: str, object_type: str, object_ids: list[int], ds_key_map: dict, ns_key_map: dict, export_data: dict
    ):
        if scope_type != ScopeType.CANVAS.value:
            return

        if object_type not in [t.value for t in CANVAS_TYPES]:
            return

        ot = ObjectType(object_type)
        model = cls.MODEL_MAP[ot]
        section_name = OBJECT_TYPE_TO_SECTION[ot]

        for canvas in model.objects.filter(id__in=object_ids):
            yaml_obj = cls.convert_canvas_to_yaml(canvas, ot, ds_key_map, ns_key_map)
            export_data[section_name].append(yaml_obj)

    @classmethod
    def export_objects(cls, scope_type: str, object_type: str, object_ids: list[int], organization_id: int = 0) -> dict:
        """
        导出对象为YAML

        参数：
        - scope_type: canvas 或 config
        - object_type: 要导出的对象类型
        - object_ids: 经过组织过滤的合法对象 ID 列表
        - organization_id: 组织ID

        返回：
        {
            "yaml_content": "<yaml_string>",
            "summary": {"exported": {...}}
        }
        """
        section_names = list(OBJECT_TYPE_TO_SECTION.values())
        export_data = {
            "meta": {
                "schema_version": YAML_SCHEMA_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": {"organization_id": organization_id},
                "object_counts": {},
            },
        }
        for section in section_names:
            export_data[section] = []

        if scope_type == ScopeType.CANVAS.value:
            collected_datasource_ids, collected_namespace_ids = cls._collect_canvas_dependencies(object_type, object_ids)
        else:
            collected_datasource_ids, collected_namespace_ids = cls._collect_config_objects(object_type, object_ids)

        ns_key_map = {}
        if collected_namespace_ids:
            namespaces = NameSpace.objects.filter(id__in=collected_namespace_ids)
            for ns in namespaces:
                ns_key_map[ns.id] = ns.name
                export_data["namespaces"].append(cls.convert_namespace_to_yaml(ns))

        ds_key_map = {}
        if collected_datasource_ids:
            datasources = DataSourceAPIModel.objects.filter(id__in=collected_datasource_ids).prefetch_related("namespaces", "tag")
            for ds in datasources:
                ds_key = cls.generate_business_key(ds, ObjectType.DATASOURCE)
                ds_key_map[ds.id] = ds_key
                export_data["datasources"].append(cls.convert_datasource_to_yaml(ds))

                for ns in ds.namespaces.all():
                    if ns.id not in ns_key_map:
                        ns_key_map[ns.id] = ns.name
                        export_data["namespaces"].append(cls.convert_namespace_to_yaml(ns))

        cls._convert_canvases_to_yaml(scope_type, object_type, object_ids, ds_key_map, ns_key_map, export_data)

        for section in section_names:
            export_data[section].sort(key=lambda x: x.get("name", ""))

        export_data["meta"]["object_counts"] = {section: len(export_data[section]) for section in section_names}

        yaml_content = yaml.dump(
            export_data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

        return {
            "yaml_content": yaml_content,
            "summary": {
                "exported": export_data["meta"]["object_counts"],
            },
        }
