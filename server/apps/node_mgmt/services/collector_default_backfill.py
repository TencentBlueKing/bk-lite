from django.db import IntegrityError, transaction

from apps.core.logger import node_mgmt_logger as logger
from apps.core.logger import safe_log_value
from apps.core.utils.safe_template import build_sandboxed_env
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.sidecar import Collector, CollectorConfiguration, Node, NodeCollectorConfiguration
from apps.node_mgmt.services.cloudregion import RegionService
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.sidecar import format_tags_dynamic

NODE_CHUNK_SIZE = 200
NODE_LIMIT_PER_RUN = 2000
CONFIG_NAME_MAX_LENGTH = 100
NODE_FAILED_LOG = "event=collector_default_backfill_node_failed node_id=%s collector_id=%s failed_stage=render error_type=%s"
_MODE_TEMPLATE_EXCLUDED_KEYS = {"add_config", "config_section"}
_NODE_ARCH_BUCKETS = (NodeConstants.ARM64_ARCH, NodeConstants.X86_64_ARCH, NodeConstants.UNKNOWN_ARCH)


def render_builtin_default_template(collector, variables, *, is_container_node):
    """按首次纳管的同一套规则渲染预置模板。没有可渲染模板时返回 None。"""
    if collector.name in CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS and not is_container_node:
        return None
    default_config = collector.default_config or {}
    if not isinstance(default_config, dict):
        return None
    mode = variables.get("SIDECAR_INPUT_MODE", "nats")
    config_template = default_config.get(mode)
    if not isinstance(config_template, str) or not config_template:
        return None
    if is_container_node:
        add_config = default_config.get("add_config", "")
        if add_config:
            config_template = config_template + "\n" + add_config
    return build_sandboxed_env().from_string(config_template).render(variables)


def _is_container_node(node):
    if node.node_type == ControllerConstants.NODE_TYPE_CONTAINER:
        return True
    if not isinstance(node.tags, list):
        return False
    parsed = format_tags_dynamic(node.tags, [ControllerConstants.NODE_TYPE_TAG])
    return ControllerConstants.NODE_TYPE_CONTAINER in parsed.get(ControllerConstants.NODE_TYPE_TAG, [])


def winning_node_architectures(collector):
    """节点架构桶：该采集器会在首次纳管时被选为同名默认采集器。"""
    from apps.node_mgmt.services.sidecar import Sidecar

    peers = list(
        Collector.objects.filter(
            controller_default_run=True,
            node_operating_system=collector.node_operating_system,
            name=collector.name,
        )
    )
    winning = []
    for node_arch in _NODE_ARCH_BUCKETS:
        allowed = set(Sidecar.allowed_collector_architectures(node_arch))
        selected = None
        selected_priority = -1
        for candidate in peers:
            if (candidate.cpu_architecture or "") not in allowed:
                continue
            priority = Sidecar._default_collector_priority(candidate.cpu_architecture, node_arch)
            if selected is None or priority > selected_priority:
                selected = candidate
                selected_priority = priority
        if selected is not None and selected.id == collector.id and selected_priority > 0:
            winning.append(node_arch)
    return winning


def _candidate_nodes(collector):
    if not winning_node_architectures(collector):
        return Node.objects.none()
    return (
        Node.objects.filter(operating_system=collector.node_operating_system)
        .exclude(
            id__in=NodeCollectorConfiguration.objects.filter(collector_config__collector_id=collector.id).values("node_id"),
        )
        .order_by("id")
        .only("id", "cpu_architecture", "node_type", "tags", "cloud_region_id")
    )


def _load_region_env(region_id, cache):
    if region_id in cache:
        cached = cache[region_id]
        if isinstance(cached, Exception):
            raise cached
        return cached
    try:
        cache[region_id] = RegionService.get_cloud_region_envconfig(region_id)
    except Exception as exc:
        cache[region_id] = exc
        raise
    return cache[region_id]


def _create_pre_config(collector, node, rendered):
    config_name = f"{collector.name}-{node.id}"
    if len(config_name) > CONFIG_NAME_MAX_LENGTH:
        raise ValueError("ConfigNameTooLong")
    with transaction.atomic():
        configuration = CollectorConfiguration.objects.create(
            name=config_name,
            collector=collector,
            config_template=rendered,
            is_pre=True,
            cloud_region_id=node.cloud_region_id,
        )
        configuration.nodes.add(node)


def execute_collector_default_backfill(collector_id, *, after_id=""):
    """为单个新内置采集器补齐缺失的预置配置。已有配置不改写。"""
    collector = Collector.objects.filter(id=collector_id).first()
    if collector is None or not collector.is_pre or not collector.controller_default_run:
        return {"created": 0, "failed": 0, "hit_limit": False, "cursor_id": "", "last_error": None}

    created = 0
    failed = 0
    processed = 0
    last_id = after_id or ""
    last_error = None
    env_cache = {}
    winning_architectures = set(winning_node_architectures(collector))
    container_only = collector.name in CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS
    candidates = _candidate_nodes(collector)
    while processed < NODE_LIMIT_PER_RUN:
        chunk = list(candidates.filter(id__gt=last_id)[: min(NODE_CHUNK_SIZE, NODE_LIMIT_PER_RUN - processed)])
        if not chunk:
            break
        last_id = chunk[-1].id
        processed += len(chunk)
        chunk_ids = [node.id for node in chunk]
        taken_names = set(
            CollectorConfiguration.objects.filter(name__in=[f"{collector.name}-{node_id}" for node_id in chunk_ids]).values_list(
                "name", flat=True
            )
        )
        for node in chunk:
            config_name = f"{collector.name}-{node.id}"
            normalized_arch = normalize_cpu_architecture(node.cpu_architecture)
            is_container_node = _is_container_node(node)
            if config_name in taken_names or normalized_arch not in winning_architectures:
                continue
            if container_only and not is_container_node:
                continue
            try:
                variables = _load_region_env(node.cloud_region_id, env_cache)
                rendered = render_builtin_default_template(
                    collector,
                    variables,
                    is_container_node=is_container_node,
                )
                if rendered is None:
                    continue
                _create_pre_config(collector, node, rendered)
                created += 1
            except IntegrityError:
                continue
            except Exception as exc:
                failed += 1
                last_error = exc
                logger.warning(
                    NODE_FAILED_LOG,
                    safe_log_value(node.id),
                    safe_log_value(collector.id),
                    type(exc).__name__,
                )
    hit_limit = processed >= NODE_LIMIT_PER_RUN and candidates.filter(id__gt=last_id).exists()
    return {
        "created": created,
        "failed": failed,
        "hit_limit": hit_limit,
        "cursor_id": last_id if hit_limit else "",
        "last_error": last_error,
    }
