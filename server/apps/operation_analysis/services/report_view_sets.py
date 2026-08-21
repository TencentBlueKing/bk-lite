from typing import Any

REPORT_SCHEMA_VERSION = 1
REPORT_COMPONENT_TYPES = frozenset({"table", "eventTable"})
REPORT_FILTER_TYPES = frozenset({"string", "timeRange", "dateRange"})


def _normalize_filter(definition: Any, index: int, seen_ids: set[str]) -> dict[str, Any]:
    path = f"filters[{index}]"
    if not isinstance(definition, dict):
        raise ValueError(f"{path} 必须是 JSON 对象")

    normalized = dict(definition)
    for field in ("id", "key", "name"):
        value = definition.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}.{field} 必须是非空字符串")
        normalized[field] = value.strip()

    filter_id = normalized["id"]
    if filter_id in seen_ids:
        raise ValueError(f"{path}.id 与其它筛选项重复")
    seen_ids.add(filter_id)

    filter_type = definition.get("type")
    if filter_type not in REPORT_FILTER_TYPES:
        raise ValueError(f"{path}.type 不支持筛选类型 '{filter_type}'")

    enabled = definition.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError(f"{path}.enabled 必须是布尔值")

    order = definition.get("order")
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise ValueError(f"{path}.order 必须是非负整数")

    if "options" in definition and not isinstance(definition["options"], list):
        raise ValueError(f"{path}.options 必须是数组")
    if "inputConfig" in definition and not isinstance(definition["inputConfig"], dict):
        raise ValueError(f"{path}.inputConfig 必须是 JSON 对象")

    return normalized


def _normalize_data_source(data_source: Any, path: str, *, allow_portable_datasource_ref: bool) -> int | str:
    if isinstance(data_source, int) and not isinstance(data_source, bool) and data_source > 0:
        return data_source
    if allow_portable_datasource_ref and isinstance(data_source, str) and data_source.strip():
        return data_source.strip()
    raise ValueError(f"{path}.valueConfig.dataSource 必须是正整数数据源 ID")


def _normalize_section(
    section: Any,
    index: int,
    seen_ids: set[str],
    *,
    allow_portable_datasource_ref: bool,
) -> dict[str, Any]:
    path = f"sections[{index}]"
    if not isinstance(section, dict):
        raise ValueError(f"{path} 必须是 JSON 对象")

    section_id = section.get("id")
    if not isinstance(section_id, str) or not section_id.strip():
        raise ValueError(f"{path}.id 必须是非空字符串")
    section_id = section_id.strip()
    if section_id in seen_ids:
        raise ValueError(f"{path}.id 与其它组件重复")
    seen_ids.add(section_id)

    value_config = section.get("valueConfig")
    if not isinstance(value_config, dict):
        raise ValueError(f"{path}.valueConfig 必须是 JSON 对象")

    chart_type = value_config.get("chartType")
    if not isinstance(chart_type, str) or not chart_type.strip():
        raise ValueError(f"{path}.valueConfig.chartType 必须是非空字符串")
    chart_type = chart_type.strip()
    if chart_type not in REPORT_COMPONENT_TYPES:
        raise ValueError(f"{path}.valueConfig.chartType 不支持报表组件类型 '{chart_type}'")

    data_source = _normalize_data_source(
        value_config.get("dataSource"),
        path,
        allow_portable_datasource_ref=allow_portable_datasource_ref,
    )
    if "dataSourceParams" in value_config and not isinstance(value_config["dataSourceParams"], list):
        raise ValueError(f"{path}.valueConfig.dataSourceParams 必须是数组")
    if "tableConfig" in value_config and not isinstance(value_config["tableConfig"], dict):
        raise ValueError(f"{path}.valueConfig.tableConfig 必须是 JSON 对象")
    for field in ("name", "description"):
        if field in value_config and not isinstance(value_config[field], str):
            raise ValueError(f"{path}.valueConfig.{field} 必须是字符串")

    return {
        "id": section_id,
        "valueConfig": {**value_config, "chartType": chart_type, "dataSource": data_source},
    }


def normalize_report_view_sets(value: Any, *, allow_portable_datasource_ref: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("view_sets 必须是 JSON 对象")

    schema_version = value.get("schema_version", REPORT_SCHEMA_VERSION)
    if schema_version != REPORT_SCHEMA_VERSION:
        raise ValueError(f"schema_version 仅支持 {REPORT_SCHEMA_VERSION}")

    filters = value.get("filters", [])
    if not isinstance(filters, list):
        raise ValueError("filters 必须是数组")

    sections = value.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError("sections 必须是数组")

    seen_filter_ids: set[str] = set()
    normalized_filters = [_normalize_filter(definition, index, seen_filter_ids) for index, definition in enumerate(filters)]
    seen_section_ids: set[str] = set()
    normalized_sections = [
        _normalize_section(
            section,
            index,
            seen_section_ids,
            allow_portable_datasource_ref=allow_portable_datasource_ref,
        )
        for index, section in enumerate(sections)
    ]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "filters": normalized_filters,
        "sections": normalized_sections,
    }
