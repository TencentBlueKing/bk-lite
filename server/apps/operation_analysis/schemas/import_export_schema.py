# -- coding: utf-8 --
"""
YAML导入导出契约校验模块

提供YAML结构校验、非法DB ID检测、业务键格式验证等功能。
校验规则与Tech Plan第3节数据结构规则严格对齐。
"""

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from apps.operation_analysis.constants.import_export import (
    BUSINESS_KEY_SEPARATOR,
    CANVAS_TYPES,
    OBJECT_TYPE_TO_SECTION,
    YAML_SCHEMA_VERSION,
    ImportExportErrorCode,
    ObjectType,
)


def _normalize_canvas_view_sets_for_storage(v, object_type):
    """延迟导入以避免循环依赖"""
    from apps.operation_analysis.services.import_export.view_sets import normalize_canvas_view_sets_for_storage

    return normalize_canvas_view_sets_for_storage(v, object_type)


class ImportExportValidationError(Exception):
    """导入导出校验异常，携带错误码与详细信息"""

    def __init__(self, code: str, message: str, details: dict = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class MetaSource(BaseModel):
    """YAML meta.source 结构"""

    organization_id: int = Field(default=0)


class YAMLMeta(BaseModel):
    """
    YAML顶层meta结构校验

    schema_version: 固定为当前 YAML_SCHEMA_VERSION，用于版本兼容性检查
    exported_at: ISO 8601格式时间戳
    source: 导出来源信息
    object_counts: 各类型对象数量统计
    """

    schema_version: str = Field(default=YAML_SCHEMA_VERSION)
    exported_at: str = Field(default="")
    source: MetaSource = Field(default_factory=MetaSource)
    object_counts: dict = Field(default_factory=dict)

    @field_validator("exported_at", mode="before")
    @classmethod
    def normalize_exported_at(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v != YAML_SCHEMA_VERSION:
            raise ImportExportValidationError(
                code=ImportExportErrorCode.YAML_SCHEMA_INVALID,
                message=f"不支持的schema版本: {v}，当前仅支持 {YAML_SCHEMA_VERSION}",
            )
        return v


class NamespaceItem(BaseModel):
    """命名空间对象结构"""

    key: str
    name: str
    domain: str
    namespace: str = Field(default="bklite")
    account: str
    password: str = Field(default="")
    enable_tls: bool = Field(default=False)
    desc: str = Field(default="")

    @field_validator("key", "name", "domain", "account")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value


class DatasourceItem(BaseModel):
    """数据源对象结构"""

    key: str
    name: str
    rest_api: str
    desc: str = Field(default="")
    is_active: bool = Field(default=True)
    params: dict | list | None = Field(default_factory=list)
    tags: list = Field(default_factory=list)
    chart_type: list = Field(default_factory=list)
    field_schema: list = Field(default_factory=list)
    namespace_keys: list = Field(default_factory=list)

    @field_validator("key", "name", "rest_api")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value


class CanvasRefs(BaseModel):
    """画布对象引用关系"""

    datasource_keys: list = Field(default_factory=list)
    namespace_keys: list = Field(default_factory=list)


class DashboardItem(BaseModel):
    """仪表盘对象结构"""

    key: str
    name: str
    desc: str = Field(default="")
    filters: list = Field(default_factory=list)
    other: dict = Field(default_factory=dict)
    view_sets: list = Field(default_factory=list)
    refs: CanvasRefs = Field(default_factory=CanvasRefs)

    @field_validator("key", "name")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value

    @field_validator("desc", mode="before")
    @classmethod
    def normalize_desc(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("view_sets", mode="before")
    @classmethod
    def normalize_view_sets(cls, v: Any) -> list:
        normalized = _normalize_canvas_view_sets_for_storage(v, ObjectType.DASHBOARD)
        return normalized if isinstance(normalized, list) else []


class TopologyItem(BaseModel):
    """拓扑图对象结构"""

    key: str
    name: str
    desc: str = Field(default="")
    other: dict = Field(default_factory=dict)
    view_sets: dict = Field(default_factory=dict)
    refs: CanvasRefs = Field(default_factory=CanvasRefs)

    @field_validator("key", "name")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value

    @field_validator("desc", mode="before")
    @classmethod
    def normalize_desc(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("view_sets", mode="before")
    @classmethod
    def normalize_view_sets(cls, v: Any) -> dict:
        return _normalize_canvas_view_sets_for_storage(v, ObjectType.TOPOLOGY)


class ArchitectureItem(BaseModel):
    """架构图对象结构"""

    key: str
    name: str
    desc: str = Field(default="")
    other: dict = Field(default_factory=dict)
    view_sets: dict = Field(default_factory=dict)
    refs: CanvasRefs = Field(default_factory=CanvasRefs)

    @field_validator("key", "name")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value

    @field_validator("desc", mode="before")
    @classmethod
    def normalize_desc(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("view_sets", mode="before")
    @classmethod
    def normalize_view_sets(cls, v: Any) -> dict:
        return _normalize_canvas_view_sets_for_storage(v, ObjectType.ARCHITECTURE)


class ScreenItem(BaseModel):
    """大屏对象结构"""

    key: str
    name: str
    desc: str = Field(default="")
    other: dict = Field(default_factory=dict)
    view_sets: dict
    refs: CanvasRefs = Field(default_factory=CanvasRefs)

    @field_validator("key", "name")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value

    @field_validator("desc", mode="before")
    @classmethod
    def normalize_desc(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("view_sets", mode="before")
    @classmethod
    def normalize_view_sets(cls, v: Any) -> dict:
        return _normalize_canvas_view_sets_for_storage(v, ObjectType.SCREEN)


class ReportItem(BaseModel):
    """报表对象结构"""

    key: str
    name: str
    desc: str = Field(default="")
    other: dict = Field(default_factory=dict)
    view_sets: dict = Field(default_factory=dict)
    refs: CanvasRefs = Field(default_factory=CanvasRefs)

    @field_validator("key", "name")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value

    @field_validator("desc", mode="before")
    @classmethod
    def normalize_desc(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("view_sets", mode="before")
    @classmethod
    def normalize_view_sets(cls, v: Any) -> dict:
        return _normalize_canvas_view_sets_for_storage(v, ObjectType.REPORT)


class YAMLDocument(BaseModel):
    """
    完整YAML文档结构校验

    允许部分章节为空或缺失，缺失章节按空列表处理。
    """

    meta: YAMLMeta = Field(default_factory=YAMLMeta)
    dashboards: list[DashboardItem] = Field(default_factory=list)
    topologies: list[TopologyItem] = Field(default_factory=list)
    architectures: list[ArchitectureItem] = Field(default_factory=list)
    screens: list[ScreenItem] = Field(default_factory=list)
    reports: list[ReportItem] = Field(default_factory=list)
    datasources: list[DatasourceItem] = Field(default_factory=list)
    namespaces: list[NamespaceItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_missing_sections(cls, values: dict) -> dict:
        """缺失章节填充为空列表"""
        for section in OBJECT_TYPE_TO_SECTION.values():
            if section not in values or values[section] is None:
                values[section] = []
        if "meta" not in values or values["meta"] is None:
            values["meta"] = {}
        return values


# 非法DB ID引用检测正则：字段名以id或ids结尾
DB_ID_FIELD_PATTERN = re.compile(r"(^|_)(id|ids)$", re.IGNORECASE)

# 纯数字值检测（可能是数据库ID）
PURE_NUMERIC_PATTERN = re.compile(r"^\d+$")


def detect_db_id_references(data: Any, path: str = "") -> list[dict]:
    """
    递归检测数据中的非法数据库ID引用

    检测规则（Tech Plan 3.5节）:
    1. 字段名命中正则 (^|_)(id|ids)$ 且属于引用语义
    2. 引用字段值为纯数字且无业务键前缀

    返回检测到的全部非法引用列表
    """
    violations = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            # 检测字段名是否为id类型字段
            if DB_ID_FIELD_PATTERN.search(key):
                # 跳过organization_id（这是meta中的合法字段）
                if key == "organization_id":
                    continue
                is_numeric_scalar = isinstance(value, int) or (isinstance(value, str) and PURE_NUMERIC_PATTERN.match(value))
                is_numeric_list = isinstance(value, list) and any(
                    isinstance(item, int) or (isinstance(item, str) and PURE_NUMERIC_PATTERN.match(item)) for item in value
                )

                if is_numeric_scalar or is_numeric_list:
                    violations.append(
                        {
                            "path": current_path,
                            "field": key,
                            "value": value,
                            "reason": "字段名疑似数据库ID引用",
                        }
                    )

            # 递归检测嵌套结构
            violations.extend(detect_db_id_references(value, current_path))

    elif isinstance(data, list):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"
            violations.extend(detect_db_id_references(item, current_path))

    return violations


def validate_business_key_format(key: str, object_type: ObjectType) -> bool:
    """
    校验业务键格式是否符合规范

    业务键规则（Tech Plan 3.2节）:
    - namespace_key = namespace.name
    - datasource_key = datasource.name + "::" + datasource.rest_api
    - dashboard_key = "dashboard::" + dashboard.name
    - topology_key = "topology::" + topology.name
    - architecture_key = "architecture::" + architecture.name
    """
    if not key:
        return False

    # 纯数字的key被认为是非法的DB ID
    if PURE_NUMERIC_PATTERN.match(key):
        return False

    # 画布类型的key必须以类型前缀开头
    if object_type in CANVAS_TYPES:
        expected_prefix = f"{object_type.value}{BUSINESS_KEY_SEPARATOR}"
        if not key.startswith(expected_prefix):
            return False

    # 数据源key必须包含分隔符
    if object_type == ObjectType.DATASOURCE:
        if BUSINESS_KEY_SEPARATOR not in key:
            return False

    return True


def count_objects(doc: YAMLDocument) -> dict:
    """统计YAML文档中各类型对象数量"""
    return {
        "total": (
            len(doc.dashboards)
            + len(doc.topologies)
            + len(doc.architectures)
            + len(doc.screens)
            + len(doc.reports)
            + len(doc.datasources)
            + len(doc.namespaces)
        ),
        "by_type": {
            ObjectType.DASHBOARD.value: len(doc.dashboards),
            ObjectType.TOPOLOGY.value: len(doc.topologies),
            ObjectType.ARCHITECTURE.value: len(doc.architectures),
            ObjectType.SCREEN.value: len(doc.screens),
            ObjectType.REPORT.value: len(doc.reports),
            ObjectType.DATASOURCE.value: len(doc.datasources),
            ObjectType.NAMESPACE.value: len(doc.namespaces),
        },
    }
