"""CMDB Model 反射工具 —— 从 apps.cmdb.tests.e2e.schemas.<model_id>/04_cmdb_instance.schema.json 反射字段定义。

用于:
  - A 端对齐检查:test_stargazer_prometheus_alignment 验证 metric label 集合 ⊇ Model 必填字段
  - B 端对齐检查:test_cmdb_vm_format_alignment 验证实例字段 ⊆ Model 字段定义 + 必填非空 + choice 合法

CMDB 实例模型(graph-backed 动态 model)字段定义实际存储在 JSON Schema 中,
不是 Django ORM Model;因此 model_reflection 从 JSON Schema 反射。
不修改 production 代码,只读取测试 schema 文件。
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# 04_cmdb_instance.schema.json 存放位置(相对 server/ 目录)
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"


@dataclass(frozen=True)
class ModelFieldDef:
    """CMDB Model 字段定义反射结果。"""
    name: str
    field_type: str  # str / int / float / bool / choice / json / datetime
    is_required: bool
    choice: Optional[list] = None


def _load_schema(model_id: str) -> dict:
    """加载 model_id 对应的 04_cmdb_instance.schema.json,不存在则抛 KeyError。"""
    schema_path = SCHEMA_ROOT / model_id / "04_cmdb_instance.schema.json"
    if not schema_path.exists():
        raise KeyError(
            f"model_id={model_id!r} 的 04_cmdb_instance.schema.json 找不到: {schema_path}"
        )
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _detect_field_type(prop_schema: dict) -> str:
    """从 JSON Schema property 推断字段类型字符串。"""
    json_type = prop_schema.get("type")
    if json_type is None:
        # 无 type 字段:可能是 $ref / anyOf 等复杂结构,默认 str
        return "str"

    # type 可能是 list(如 ["string", "integer"] 表示兼容类型)
    if isinstance(json_type, list):
        # 兼容类型:按优先级推断
        if "integer" in json_type or "number" in json_type:
            if "string" in json_type:
                return "str"  # str_or_int 兼容,默认 str(Django 风格)
        if "boolean" in json_type:
            return "bool"
        if "object" in json_type or "array" in json_type:
            return "json"
        return "str"

    type_map = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "object": "json",
        "array": "json",
        "null": "unknown",
    }
    return type_map.get(json_type, "unknown")


def _detect_choice(prop_schema: dict) -> Optional[list]:
    """从 JSON Schema property 提取 choice 列表(enum 约束)。"""
    enum = prop_schema.get("enum")
    if enum and isinstance(enum, list):
        return [str(v) for v in enum]
    return None


def get_model_field_def(model_id: str) -> dict[str, ModelFieldDef]:
    """从 04_cmdb_instance.schema.json 反射 model_id 的字段定义。

    Returns:
        {field_name: ModelFieldDef} 字典

    Raises:
        KeyError: model_id 的 04_cmdb_instance.schema.json 不存在
    """
    schema = _load_schema(model_id)
    required_set = set(schema.get("required", []))
    properties = schema.get("properties", {})

    fields: dict[str, ModelFieldDef] = {}
    for field_name, prop_schema in properties.items():
        field_type = _detect_field_type(prop_schema)
        is_required = field_name in required_set
        choice = _detect_choice(prop_schema)

        fields[field_name] = ModelFieldDef(
            name=field_name,
            field_type=field_type,
            is_required=is_required,
            choice=choice,
        )

    return fields
