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


def collect_named_option_datasource_ids_from_filters(filters) -> set[int]:
    """从画布筛选项 inputConfig 收集能点名的动态选项源。"""
    source_ids, rest_apis = _collect_option_refs(_iter_dynamic_options_sources(filters if isinstance(filters, list) else []))
    return _resolve_option_datasource_ids(source_ids, rest_apis)


def collect_named_option_datasource_ids_by_primary(primary_ids: Iterable[int]) -> dict[int, set[int]]:
    """从主数据源 params 收集能点名的动态选项源。

    sourceId：仅收录库中存在的 id。
    sourceRef.rest_api：仅在全表恰好一条，或恰好一条内置时收录，避免同 path 全表放行。
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

    resolved_rest_apis = _resolve_unique_rest_api_ids({item for values in rest_apis_by_primary.values() for item in values})
    for ds_id, apis in rest_apis_by_primary.items():
        for rest_api in apis:
            resolved = resolved_rest_apis.get(rest_api)
            if resolved is not None:
                result[ds_id].add(resolved)
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
    return sources


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
    return source_ids, rest_apis


def _resolve_option_datasource_ids(source_ids: set[int], rest_apis: set[str]) -> set[int]:
    resolved: set[int] = set()
    if source_ids:
        resolved.update(DataSourceAPIModel.objects.filter(id__in=source_ids).values_list("id", flat=True))
    resolved.update(_resolve_unique_rest_api_ids(rest_apis).values())
    return resolved


def _resolve_unique_rest_api_ids(rest_apis: set[str]) -> dict[str, int]:
    if not rest_apis:
        return {}
    grouped: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    for ds_id, rest_api, is_build_in in DataSourceAPIModel.objects.filter(rest_api__in=rest_apis).values_list(
        "id",
        "rest_api",
        "is_build_in",
    ):
        grouped[rest_api].append((ds_id, bool(is_build_in)))

    resolved: dict[str, int] = {}
    for rest_api, matches in grouped.items():
        if len(matches) == 1:
            resolved[rest_api] = matches[0][0]
            continue
        builtins = [ds_id for ds_id, is_build_in in matches if is_build_in]
        if len(builtins) == 1:
            resolved[rest_api] = builtins[0]
    return resolved
