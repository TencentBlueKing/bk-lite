from typing import Any

from apps.operation_analysis.services.user_messages import oa_message

REPORT_SCHEMA_VERSION = 1
REPORT_COMPONENT_TYPES = frozenset({"table", "eventTable"})
REPORT_FILTER_TYPES = frozenset({"string", "timeRange", "dateRange", "number"})


def _normalize_filter(definition: Any, index: int, seen_ids: set[str]) -> dict[str, Any]:
    path = f"filters[{index}]"
    if not isinstance(definition, dict):
        raise ValueError(oa_message("messages.path_json_object", "{path} 必须是 JSON 对象", path=path))

    normalized = dict(definition)
    for field in ("id", "key", "name"):
        value = definition.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(oa_message("messages.path_nonempty_string", "{path} 必须是非空字符串", path=f"{path}.{field}"))
        normalized[field] = value.strip()

    filter_id = normalized["id"]
    if filter_id in seen_ids:
        raise ValueError(oa_message("messages.path_filter_id_duplicate", "{path} 与其它筛选项重复", path=f"{path}.id"))
    seen_ids.add(filter_id)

    filter_type = definition.get("type")
    if filter_type not in REPORT_FILTER_TYPES:
        raise ValueError(oa_message("messages.path_filter_type", "{path} 不支持筛选类型 '{filter_type}'", path=f"{path}.type", filter_type=filter_type))

    enabled = definition.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError(oa_message("messages.path_must_be_bool", "{path} 必须是布尔值", path=f"{path}.enabled"))

    order = definition.get("order")
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise ValueError(oa_message("messages.path_order_nonneg", "{path} 必须是非负整数", path=f"{path}.order"))

    if "options" in definition and not isinstance(definition["options"], list):
        raise ValueError(oa_message("messages.path_must_be_array", "{path} 必须是数组", path=f"{path}.options"))
    if "inputConfig" in definition and not isinstance(definition["inputConfig"], dict):
        raise ValueError(oa_message("messages.path_json_object", "{path} 必须是 JSON 对象", path=f"{path}.inputConfig"))

    return normalized


def _normalize_data_source(data_source: Any, path: str, *, allow_portable_datasource_ref: bool) -> int | str:
    if isinstance(data_source, int) and not isinstance(data_source, bool) and data_source > 0:
        return data_source
    if allow_portable_datasource_ref and isinstance(data_source, str) and data_source.strip():
        return data_source.strip()
    raise ValueError(oa_message("messages.report_datasource_id", "{path} 必须是正整数数据源 ID", path=f"{path}.valueConfig.dataSource"))


def _normalize_section(
    section: Any,
    index: int,
    seen_ids: set[str],
    *,
    allow_portable_datasource_ref: bool,
) -> dict[str, Any]:
    path = f"sections[{index}]"
    if not isinstance(section, dict):
        raise ValueError(oa_message("messages.path_json_object", "{path} 必须是 JSON 对象", path=path))

    section_id = section.get("id")
    if not isinstance(section_id, str) or not section_id.strip():
        raise ValueError(oa_message("messages.path_nonempty_string", "{path} 必须是非空字符串", path=f"{path}.id"))
    section_id = section_id.strip()
    if section_id in seen_ids:
        raise ValueError(oa_message("messages.path_widget_id_duplicate", "{path} 与其它组件重复", path=f"{path}.id"))
    seen_ids.add(section_id)

    value_config = section.get("valueConfig")
    if not isinstance(value_config, dict):
        raise ValueError(oa_message("messages.path_json_object", "{path} 必须是 JSON 对象", path=f"{path}.valueConfig"))

    chart_type = value_config.get("chartType")
    if not isinstance(chart_type, str) or not chart_type.strip():
        raise ValueError(oa_message("messages.path_chart_type_required", "{path} 必须是非空字符串", path=f"{path}.valueConfig.chartType"))
    chart_type = chart_type.strip()
    if chart_type not in REPORT_COMPONENT_TYPES:
        raise ValueError(
            oa_message(
                "messages.path_chart_type_unsupported", "{path} 不支持报表组件类型 '{chart_type}'", path=f"{path}.valueConfig.chartType", chart_type=chart_type
            )
        )

    data_source = _normalize_data_source(
        value_config.get("dataSource"),
        path,
        allow_portable_datasource_ref=allow_portable_datasource_ref,
    )
    if "dataSourceParams" in value_config and not isinstance(value_config["dataSourceParams"], list):
        raise ValueError(oa_message("messages.path_must_be_array", "{path} 必须是数组", path=f"{path}.valueConfig.dataSourceParams"))
    if "tableConfig" in value_config and not isinstance(value_config["tableConfig"], dict):
        raise ValueError(oa_message("messages.path_json_object", "{path} 必须是 JSON 对象", path=f"{path}.valueConfig.tableConfig"))
    for field in ("name", "description"):
        if field in value_config and not isinstance(value_config[field], str):
            raise ValueError(oa_message("messages.path_must_be_string", "{path} 必须是字符串", path=f"{path}.valueConfig.{field}"))

    return {
        "id": section_id,
        "valueConfig": {**value_config, "chartType": chart_type, "dataSource": data_source},
    }


def normalize_report_view_sets(value: Any, *, allow_portable_datasource_ref: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(oa_message("messages.view_sets_json_object", "view_sets 必须是 JSON 对象"))

    schema_version = value.get("schema_version", REPORT_SCHEMA_VERSION)
    if schema_version != REPORT_SCHEMA_VERSION:
        raise ValueError(oa_message("messages.schema_version_only", "schema_version 仅支持 {version}", version=REPORT_SCHEMA_VERSION))

    filters = value.get("filters", [])
    if not isinstance(filters, list):
        raise ValueError(oa_message("messages.filters_must_be_array", "filters 必须是数组"))

    sections = value.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError(oa_message("messages.sections_must_be_array", "sections 必须是数组"))

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
