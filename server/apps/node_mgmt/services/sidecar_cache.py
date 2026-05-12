from collections.abc import Iterable

from django.core.cache import cache
from django.db import transaction


NODE_ETAG_CACHE_PREFIX = "node_etag_"
CONFIGURATION_ETAG_CACHE_PREFIX = "configuration_etag_"
SIDECARENV_CACHE_PREFIX = "sidecar_env_cache_"
ASSIGNMENT_ETAG_INVALIDATION_ACTIONS = {"post_add", "post_remove", "pre_clear"}


def build_configuration_etag_cache_key(node_id, configuration_id):
    return f"{CONFIGURATION_ETAG_CACHE_PREFIX}{node_id}_{configuration_id}"


def build_sidecar_env_cache_key(cloud_region_id):
    return f"{SIDECARENV_CACHE_PREFIX}{cloud_region_id}"


def _normalize_ids(ids: Iterable | None) -> list[str]:
    if not ids:
        return []

    normalized = []
    seen = set()
    for item in ids:
        if item is None:
            continue
        value = str(item)
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def invalidate_node_etags(node_ids: Iterable | None):
    keys = [f"{NODE_ETAG_CACHE_PREFIX}{node_id}" for node_id in _normalize_ids(node_ids)]
    if keys:
        transaction.on_commit(lambda: cache.delete_many(keys))


def invalidate_sidecar_env_cache(cloud_region_ids: Iterable | None):
    keys = [build_sidecar_env_cache_key(cloud_region_id) for cloud_region_id in _normalize_ids(cloud_region_ids)]
    if keys:
        transaction.on_commit(lambda: cache.delete_many(keys))


def _configuration_etag_keys(configuration_ids: Iterable | None, node_ids: Iterable | None):
    normalized_configuration_ids = _normalize_ids(configuration_ids)
    normalized_node_ids = _normalize_ids(node_ids)
    return [
        build_configuration_etag_cache_key(node_id, configuration_id)
        for configuration_id in normalized_configuration_ids
        for node_id in normalized_node_ids
    ]


def _configuration_node_map(configuration_ids: Iterable | None):
    normalized_configuration_ids = _normalize_ids(configuration_ids)
    if not normalized_configuration_ids:
        return {}

    from apps.node_mgmt.models.sidecar import NodeCollectorConfiguration

    configuration_node_map = {configuration_id: [] for configuration_id in normalized_configuration_ids}
    assignments = NodeCollectorConfiguration.objects.filter(collector_config_id__in=normalized_configuration_ids).values_list(
        "collector_config_id",
        "node_id",
    )
    for configuration_id, node_id in assignments:
        configuration_node_map.setdefault(str(configuration_id), []).append(str(node_id))
    return configuration_node_map


def invalidate_configuration_etag(configuration_id, node_ids: Iterable | None = None):
    if configuration_id is None:
        return

    keys = _configuration_etag_keys([configuration_id], node_ids)
    if not keys and node_ids is None:
        keys = _configuration_etag_keys([configuration_id], _configuration_node_map([configuration_id]).get(str(configuration_id), []))

    if keys:
        transaction.on_commit(lambda: cache.delete_many(keys))


def invalidate_configuration_etags(configuration_ids: Iterable | None):
    configuration_node_map = _configuration_node_map(configuration_ids)
    keys = []
    for configuration_id, node_ids in configuration_node_map.items():
        keys.extend(_configuration_etag_keys([configuration_id], node_ids))
    if keys:
        transaction.on_commit(lambda: cache.delete_many(keys))


def invalidate_bulk_config_node_etags(configs: Iterable | None):
    invalidate_node_etags([config.get("node_id") for config in configs or [] if isinstance(config, dict)])


def invalidate_bulk_child_config_etags(child_configs: Iterable | None):
    invalidate_configuration_etags(
        {
            config.get("collector_config_id")
            for config in child_configs or []
            if isinstance(config, dict) and config.get("collector_config_id") is not None
        }
    )


def _node_ids_from_assignment_clear(instance):
    nodes_manager = getattr(instance, "nodes", None)
    if not nodes_manager:
        return []
    return list(nodes_manager.values_list("id", flat=True))


def _configuration_ids_from_assignment_clear(instance):
    configurations_manager = getattr(instance, "collectorconfiguration_set", None)
    if not configurations_manager:
        return []
    return list(configurations_manager.values_list("id", flat=True))


def invalidate_assignment_node_etags(action, reverse, instance, pk_set):
    if action not in ASSIGNMENT_ETAG_INVALIDATION_ACTIONS:
        return

    if reverse:
        invalidate_node_etags([getattr(instance, "pk", None)])
        return

    node_ids = pk_set if pk_set is not None else _node_ids_from_assignment_clear(instance)
    invalidate_node_etags(node_ids)


def invalidate_assignment_configuration_etags(action, reverse, instance, pk_set):
    if action not in ASSIGNMENT_ETAG_INVALIDATION_ACTIONS:
        return

    if reverse:
        configuration_ids = pk_set if pk_set is not None else _configuration_ids_from_assignment_clear(instance)
        keys = _configuration_etag_keys(configuration_ids, [getattr(instance, "pk", None)])
    else:
        keys = _configuration_etag_keys([getattr(instance, "pk", None)], pk_set if pk_set is not None else _node_ids_from_assignment_clear(instance))

    if keys:
        transaction.on_commit(lambda: cache.delete_many(keys))


def invalidate_action_node_etag(instance):
    node_id = getattr(instance, "node_id", None)
    if node_id is None and getattr(instance, "node", None) is not None:
        node_id = getattr(instance.node, "pk", None)
    invalidate_node_etags([node_id])


def invalidate_child_config_etag(instance):
    configuration_id = getattr(instance, "collector_config_id", None)
    if configuration_id is None and getattr(instance, "collector_config", None) is not None:
        configuration_id = getattr(instance.collector_config, "pk", None)
    invalidate_configuration_etag(configuration_id)


def invalidate_collector_configuration_etag(instance):
    invalidate_configuration_etag(getattr(instance, "pk", None), node_ids=_node_ids_from_assignment_clear(instance))


def invalidate_collector_configuration_node_etags(instance):
    invalidate_node_etags(_node_ids_from_assignment_clear(instance))


def invalidate_collector_configuration_related_etags(instance):
    invalidate_collector_configuration_etag(instance)
    invalidate_collector_configuration_node_etags(instance)
