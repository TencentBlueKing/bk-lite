from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

UNIFIED_FILTER_MANIFEST_WIDGET_ID = "__unified_filter__"


def collect_named_option_datasource_ids(primary_ids: Iterable[int]) -> set[int]:
    extras: set[int] = set()
    for option_ids in collect_named_option_datasource_ids_by_primary(primary_ids).values():
        extras.update(option_ids)
    return extras


def _filter_option_refs(filters) -> set[str]:
    sources = _iter_dynamic_options_sources(filters if isinstance(filters, list) else [])
    _source_ids, rest_apis = _collect_option_refs(sources)
    return rest_apis


def collect_named_option_datasource_ids_from_filters(filters) -> set[int]:
    """从画布筛选项 inputConfig 收集能点名的动态选项源。"""
    source_ids, rest_apis = _collect_option_refs(_iter_dynamic_options_sources(filters if isinstance(filters, list) else []))
    return _resolve_option_datasource_ids(source_ids, rest_apis)


def collect_named_option_datasource_ids_by_primary(primary_ids: Iterable[int]) -> dict[int, set[int]]:
    """从主数据源 params 收集能点名的动态选项源。

    sourceId：仅收录库中存在的 id。
    sourceRef：全表恰好一条，或内置键恰好一条时收录。多条不猜测。
    """
    ids = {int(item) for item in primary_ids}
    result: dict[int, set[int]] = {ds_id: set() for ds_id in ids}
    if not ids:
        return result

    source_ids_by_primary: dict[int, set[int]] = defaultdict(set)
    rest_apis_by_primary: dict[int, set[str]] = defaultdict(set)
    for ds_id, params in DataSourceAPIModel.objects.filter(id__in=ids).values_list("id", "params"):
        source_ids, rest_apis = _collect_option_refs(_iter_dynamic_options_sources(params if isinstance(params, list) else []))
        source_ids_by_primary[ds_id].update(source_ids)
        rest_apis_by_primary[ds_id].update(rest_apis)

    all_source_ids = {item for values in source_ids_by_primary.values() for item in values}
    existing_source_ids: set[int] = set()
    if all_source_ids:
        existing_source_ids = set(DataSourceAPIModel.objects.filter(id__in=all_source_ids).values_list("id", flat=True))
    for ds_id, candidates in source_ids_by_primary.items():
        result[ds_id].update(candidates & existing_source_ids)

    option_refs = {item for values in rest_apis_by_primary.values() for item in values}
    resolved_rest_apis = _resolve_unique_rest_api_ids(option_refs)
    resolved_builtin_keys = _resolve_unique_builtin_key_ids(option_refs)
    for ds_id, apis in rest_apis_by_primary.items():
        for rest_api in apis:
            resolved = resolved_rest_apis.get(rest_api)
            if resolved is not None:
                result[ds_id].add(resolved)
            builtin_id = resolved_builtin_keys.get(rest_api)
            if builtin_id is not None:
                result[ds_id].add(builtin_id)
    return result


def expand_widget_manifest_with_named_option_datasources(
    manifest: list[dict] | None,
    filters=None,
) -> list[dict]:
    """在 widget_manifest 追加能点名的选项源 identity，字段仍是 identity + datasource_id。"""
    if not manifest:
        expanded = list(manifest or [])
    else:
        primary_ids: list[int] = []
        for item in manifest:
            if not isinstance(item, dict) or item.get("datasource_id") is None:
                continue
            try:
                primary_ids.append(int(item["datasource_id"]))
            except (TypeError, ValueError):
                continue

        extras_by_primary = collect_named_option_datasource_ids_by_primary(primary_ids)
        expanded = list(manifest)
        seen = {(item.get("widget_id"), item.get("datasource_id")) for item in manifest if isinstance(item, dict)}
        for item in manifest:
            if not isinstance(item, dict) or item.get("datasource_id") is None:
                continue
            try:
                primary = int(item["datasource_id"])
            except (TypeError, ValueError):
                continue
            for extra_id in extras_by_primary.get(primary, ()):
                key = (item.get("widget_id"), extra_id)
                if key in seen:
                    continue
                seen.add(key)
                expanded.append(
                    {
                        "widget_id": item.get("widget_id"),
                        "widget_type": item.get("widget_type"),
                        "datasource_id": extra_id,
                    }
                )

    filter_ids = collect_named_option_datasource_ids_from_filters(filters)
    seen_ids = {item.get("datasource_id") for item in expanded if isinstance(item, dict)}
    for extra_id in sorted(filter_ids):
        if extra_id in seen_ids:
            continue
        seen_ids.add(extra_id)
        expanded.append(
            {
                "widget_id": UNIFIED_FILTER_MANIFEST_WIDGET_ID,
                "widget_type": "unifiedFilter",
                "datasource_id": extra_id,
            }
        )
    return expanded


def iter_input_config_carriers(value) -> list[dict]:
    """画出布上带 inputConfig 的参数或筛选项，含组件参数和嵌套布局。"""
    found: list[dict] = []

    def visit(node):
        if isinstance(node, dict):
            if isinstance(node.get("inputConfig"), dict):
                found.append(node)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return found


def collect_named_option_datasource_ids_from_tree(value) -> set[int]:
    """从布局树里的组件参数收集能点名的动态选项源和条件字段源。"""
    return collect_named_option_datasource_ids_from_filters(iter_input_config_carriers(value))


def declared_option_query_keys(items) -> dict[int, set[str]]:
    """已解析的动态选项源或条件字段源，对应画布在 queryParams 里声明的参数名。

    解析不到、或同一引用有多条时，不把参数名挂到任何数据源上。
    """
    grouped: dict[int, set[str]] = defaultdict(set)
    for source in _iter_dynamic_options_sources(items if isinstance(items, list) else []):
        names = _query_param_names(source)
        if not names:
            continue
        source_ids, refs = _collect_option_refs([source])
        for resolved_id in _resolve_option_datasource_ids(source_ids, refs):
            grouped[resolved_id].update(names)
    return grouped


def _iter_dynamic_options_sources(items: Iterable) -> list[dict]:
    sources: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        input_config = item.get("inputConfig")
        if not isinstance(input_config, dict):
            continue
        options_source = input_config.get("optionsSource")
        if isinstance(options_source, dict) and options_source.get("type") == "dynamic":
            sources.append(options_source)
        if input_config.get("control") != "conditionFilter":
            continue
        fields = input_config.get("fields")
        if isinstance(fields, dict) and fields.get("kind") == "dynamic":
            sources.append(fields)
    return sources


def _query_param_names(source: dict) -> set[str]:
    raw = source.get("queryParams")
    if not isinstance(raw, dict):
        return set()
    return {key.strip() for key in raw if isinstance(key, str) and key.strip()}


def _collect_option_refs(options_sources: Iterable[dict]) -> tuple[set[int], set[str]]:
    source_ids: set[int] = set()
    rest_apis: set[str] = set()
    for options_source in options_sources:
        source_id = options_source.get("sourceId")
        if source_id is not None:
            try:
                parsed = int(source_id)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                source_ids.add(parsed)
        source_ref = options_source.get("sourceRef")
        if isinstance(source_ref, dict) and source_ref.get("type") == "rest_api":
            value = source_ref.get("value")
            if isinstance(value, str) and value:
                rest_apis.add(value)
        builtin_key = options_source.get("builtinKey")
        if isinstance(builtin_key, str) and builtin_key.strip():
            rest_apis.add(builtin_key.strip())
    return source_ids, rest_apis


def _resolve_option_datasource_ids(source_ids: set[int], rest_apis: set[str]) -> set[int]:
    resolved: set[int] = set()
    if source_ids:
        resolved.update(DataSourceAPIModel.objects.filter(id__in=source_ids).values_list("id", flat=True))
    resolved.update(_resolve_unique_rest_api_ids(rest_apis).values())
    resolved.update(_resolve_unique_builtin_key_ids(rest_apis).values())
    return resolved


def _resolve_unique_builtin_key_ids(refs: set[str]) -> dict[str, int]:
    """sourceRef 等于不可变 build_in_key 且全表只有一条时才认。同键多条不猜测。"""
    if not refs:
        return {}
    grouped: dict[str, list[int]] = defaultdict(list)
    for key, row_id in DataSourceAPIModel.objects.filter(build_in_key__in=refs, is_build_in=True).values_list(
        "build_in_key",
        "id",
    ):
        grouped[key].append(row_id)
    return {key: row_ids[0] for key, row_ids in grouped.items() if len(row_ids) == 1}


def ambiguous_source_refs(refs: set[str]) -> set[str]:
    """同一引用对应多条数据源时返回这些引用。零条或恰好一条都不是歧义。"""
    if not refs:
        return set()
    rest_groups: dict[str, list[int]] = defaultdict(list)
    for row_id, rest_api in DataSourceAPIModel.objects.filter(rest_api__in=refs).values_list("id", "rest_api"):
        rest_groups[rest_api].append(row_id)
    builtin_groups: dict[str, list[int]] = defaultdict(list)
    for key, row_id in DataSourceAPIModel.objects.filter(build_in_key__in=refs, is_build_in=True).values_list(
        "build_in_key",
        "id",
    ):
        builtin_groups[key].append(row_id)
    ambiguous: set[str] = set()
    for ref in refs:
        rest_ids = rest_groups.get(ref, [])
        builtin_ids = builtin_groups.get(ref, [])
        if len(rest_ids) > 1 or len(builtin_ids) > 1:
            ambiguous.add(ref)
        elif len(rest_ids) == 1 and len(builtin_ids) == 1 and rest_ids[0] != builtin_ids[0]:
            ambiguous.add(ref)
    return ambiguous


def raise_if_option_refs_ambiguous(refs: set[str]) -> None:
    if not ambiguous_source_refs(refs):
        return
    from apps.operation_analysis.schemas.import_export_schema import ImportExportValidationError
    from apps.operation_analysis.services.user_messages import oa_message

    raise ImportExportValidationError(
        "OA_EXPORT_OPTION_SOURCE_AMBIGUOUS",
        oa_message(
            "messages.export_option_source_ambiguous",
            "选项来源对应多个数据源，无法确定导出依赖。",
        ),
    )


def _resolve_unique_rest_api_ids(rest_apis: set[str]) -> dict[str, int]:
    """同地址恰好一条才认。多条时不挑内置、不按名称或参数猜测。"""
    if not rest_apis:
        return {}
    grouped: dict[str, list[int]] = defaultdict(list)
    for ds_id, rest_api in DataSourceAPIModel.objects.filter(rest_api__in=rest_apis).values_list("id", "rest_api"):
        grouped[rest_api].append(ds_id)
    return {rest_api: row_ids[0] for rest_api, row_ids in grouped.items() if len(row_ids) == 1}
