"""default_config 变化时，按批改写该采集器已有的预置正文。"""

import time
from types import SimpleNamespace

from apps.core.logger import node_mgmt_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.node_mgmt.models.sidecar import CollectorConfiguration, NodeCollectorConfiguration
from apps.node_mgmt.services.collector_default_backfill import is_container_node, load_region_env, render_builtin_default_template
from apps.node_mgmt.services.sidecar_cache import invalidate_configuration_etags

PRESET_REFRESH_BATCH_SIZE = 500
COMPLETED_LOG = "event=collector_preset_refresh_completed collector_id=%s checked=%s updated=%s skipped=%s elapsed_ms=%s"
FAILED_LOG = "event=collector_preset_refresh_failed collector_id=%s failed_stage=%s error_type=%s"
ETAG_FAILED_LOG = "event=collector_preset_refresh_etag_invalidate_failed collector_id=%s error_type=%s"
INCONSISTENT_BINDING_LOG = "event=collector_preset_refresh_skipped_inconsistent_binding collector_id=%s configuration_id=%s"


def refresh_collector_presets(collector, new_default_config):
    """用新的 default_config 刷新 is_pre 正文。失败时调用方必须保留目录里的旧值。"""
    stage = "load"
    started = time.perf_counter()
    checked = 0
    updated = 0
    shadow = SimpleNamespace(id=collector.id, name=collector.name, default_config=new_default_config)
    env_cache = {}
    rendered_groups = {}
    last_id = ""
    try:
        while True:
            stage = "load"
            batch = list(
                CollectorConfiguration.objects.filter(
                    collector_id=collector.id,
                    is_pre=True,
                    id__gt=last_id,
                )
                .order_by("id")
                .only("id", "config_template")[:PRESET_REFRESH_BATCH_SIZE]
            )
            if not batch:
                break
            bindings = _bindings_by_config([row.id for row in batch])
            stage = "render"
            changed = []
            for config in batch:
                checked += 1
                rendered = _rendered_preset(
                    config,
                    bindings.get(config.id, []),
                    shadow,
                    env_cache,
                    rendered_groups,
                )
                # None：容器专用采集器遇到非容器节点，或没有可渲染模板。不能写成空正文。
                if rendered is None or rendered == config.config_template:
                    continue
                config.config_template = rendered
                changed.append(config)
            if changed:
                stage = "write"
                CollectorConfiguration.objects.bulk_update(changed, ["config_template"])
                updated += len(changed)
                _invalidate_preset_etags(collector.id, changed)
            last_id = batch[-1].id
            if len(batch) < PRESET_REFRESH_BATCH_SIZE:
                break
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            COMPLETED_LOG,
            safe_log_value(collector.id),
            checked,
            updated,
            checked - updated,
            elapsed_ms,
        )
        return True
    except Exception as exc:
        logger.error(
            FAILED_LOG,
            safe_log_value(collector.id),
            stage,
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return False


def _bindings_by_config(config_ids):
    grouped = {}
    rows = NodeCollectorConfiguration.objects.filter(collector_config_id__in=config_ids).values_list(
        "collector_config_id",
        "node__node_type",
        "node__tags",
        "node__cloud_region_id",
    )
    for config_id, node_type, tags, region_id in rows:
        grouped.setdefault(config_id, []).append(
            SimpleNamespace(node_type=node_type, tags=tags, cloud_region_id=region_id),
        )
    return grouped


def _rendered_preset(config, nodes, shadow, env_cache, rendered_groups):
    if not nodes:
        return None
    signatures = {(node.cloud_region_id, is_container_node(node)) for node in nodes}
    if len(signatures) != 1:
        logger.debug(
            INCONSISTENT_BINDING_LOG,
            safe_log_value(shadow.id),
            safe_log_value(config.id),
        )
        return None
    region_id, container_node = next(iter(signatures))
    key = (region_id, container_node)
    if key not in rendered_groups:
        variables = load_region_env(region_id, env_cache)
        rendered_groups[key] = render_builtin_default_template(
            shadow,
            variables,
            is_container_node=container_node,
        )
    return rendered_groups[key]


def _invalidate_preset_etags(collector_id, configs):
    try:
        # bulk_update 不触发 post_save，ETag 要在这里清。
        invalidate_configuration_etags([config.id for config in configs])
    except Exception as exc:
        logger.warning(
            ETAG_FAILED_LOG,
            safe_log_value(collector_id),
            type(exc).__name__,
        )
