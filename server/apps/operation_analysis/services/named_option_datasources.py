from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel


def collect_named_option_datasource_ids(primary_ids: Iterable[int]) -> set[int]:
    extras: set[int] = set()
    for option_ids in collect_named_option_datasource_ids_by_primary(primary_ids).values():
        extras.update(option_ids)
    return extras


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
        if not isinstance(params, list):
            continue
        for param in params:
            if not isinstance(param, dict):
                continue
            input_config = param.get("inputConfig")
            if not isinstance(input_config, dict):
                continue
            options_source = input_config.get("optionsSource")
            if not isinstance(options_source, dict) or options_source.get("type") != "dynamic":
                continue
            source_id = options_source.get("sourceId")
            if source_id is not None:
                try:
                    parsed = int(source_id)
                except (TypeError, ValueError):
                    parsed = None
                if parsed is not None:
                    source_ids_by_primary[ds_id].add(parsed)
            source_ref = options_source.get("sourceRef")
            if isinstance(source_ref, dict) and source_ref.get("type") == "rest_api":
                value = source_ref.get("value")
                if isinstance(value, str) and value:
                    rest_apis_by_primary[ds_id].add(value)

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


def expand_widget_manifest_with_named_option_datasources(manifest: list[dict] | None) -> list[dict]:
    """在 widget_manifest 追加能点名的选项源 identity，字段仍是 identity + datasource_id。"""
    if not manifest:
        return list(manifest or [])

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
    return expanded


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
