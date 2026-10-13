"""日志只读查询。组织集合只接受网关注入。"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.utils.time_util import format_rfc3339_utc
from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.services.search import SearchService

LOG_SEARCH_WINDOW = timedelta(hours=1)
MESSAGE_LIMIT = 2048
FIELD_LIMIT = 512
MAX_FIELDS = 32
_SKIPPED_FIELDS = {"message", "_time", "_msg", "log_message", "raw_message", "trap_message"}


def team_ids(team):
    ids = []
    for item in team or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.append(value)
    return ids


def list_groups(*, team, page, page_size, keyword):
    ids = team_ids(team)
    if not ids:
        return _page(LogGroup.objects.none(), page, page_size)
    owned = LogGroupOrganization.objects.filter(organization__in=ids).values("log_group_id")
    queryset = LogGroup.objects.filter(id__in=owned).order_by("name", "id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword))
    return _page(queryset, page, page_size)


def search_logs(*, team, log_group_id, start, end, query="*", limit=20):
    start, end = _aware(start), _aware(end)
    if end <= start:
        return {"result": False, "message": "开始时间必须早于结束时间"}
    if end - start > LOG_SEARCH_WINDOW:
        return {"result": False, "message": "查询时间范围不能超过 1 小时"}
    group = _owned_group(team, log_group_id)
    if group is None:
        return {"result": False, "message": "日志分组不存在"}
    try:
        rows = SearchService.search_logs(
            query or "*",
            format_rfc3339_utc(start),
            format_rfc3339_utc(end),
            limit,
            [group.id],
            resolved_groups=[group],
        )
    except Exception:
        return {"result": False, "message": "日志查询失败"}
    if not isinstance(rows, list):
        return {"result": False, "message": "日志查询失败"}
    return {"items": [_public_event(row) for row in rows[:limit]], "limit": limit}


def _owned_group(team, log_group_id):
    ids = team_ids(team)
    if not ids:
        return None
    return (
        LogGroup.objects.filter(
            id=log_group_id,
            loggrouporganization__organization__in=ids,
        )
        .distinct()
        .first()
    )


def _page(queryset, page, page_size):
    total = queryset.count()
    start = (page - 1) * page_size
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [{"id": row.id, "name": row.name} for row in queryset[start : start + page_size]],
    }


def _public_event(event):
    if not isinstance(event, dict):
        return {"message": "", "fields": {}, "truncated": False}
    message = event.get("message")
    text = message if isinstance(message, str) else ""
    truncated = len(text) > MESSAGE_LIMIT
    fields = {}
    for key, value in event.items():
        if key in _SKIPPED_FIELDS or not isinstance(key, str):
            continue
        if isinstance(value, (dict, list)) or value is None:
            truncated = True
            continue
        if not isinstance(value, (str, int, float, bool)):
            truncated = True
            continue
        rendered = value[:FIELD_LIMIT] if isinstance(value, str) else value
        if isinstance(value, str) and len(value) > FIELD_LIMIT:
            truncated = True
        fields[key[:64]] = rendered
        if len(fields) >= MAX_FIELDS:
            truncated = True
            break
    item = {"message": text[:MESSAGE_LIMIT], "fields": fields, "truncated": truncated}
    timestamp = event.get("_time")
    if isinstance(timestamp, (str, int, float)):
        item["time"] = timestamp if not isinstance(timestamp, str) else timestamp[:64]
    return item


def _aware(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.utc)
    return value


def _rejected(message):
    return {"result": False, "message": message}


def _public_message(exc, fallback):
    text = str(exc)
    lowered = text.lower()
    if "http" in lowered or "token" in lowered or "password" in lowered or len(text) > 200:
        return fallback
    return text or fallback


def _run(action, fallback):
    from apps.core.exceptions.base_app_exception import BaseAppException

    try:
        return action()
    except BaseAppException as exc:
        return _rejected(_public_message(exc, fallback))
    except Exception:
        return _rejected(fallback)


def list_collect_types(*, team, page, page_size, keyword):
    from apps.log.models import CollectType

    if not team_ids(team):
        return _collect_type_page(CollectType.objects.none(), page, page_size)
    queryset = CollectType.objects.exclude(collector="Packetbeat", name="http").order_by("id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))
    return _collect_type_page(queryset, page, page_size)


def create_collect_instances(*, team, collect_type_id, instances, configs=None):
    from apps.log.models import CollectType
    from apps.log.services.collect_type import CollectTypeService
    from apps.node_mgmt.models import NodeOrganization

    ids = team_ids(team)
    if not ids or not CollectType.objects.filter(id=collect_type_id).exists():
        return _rejected("采集类型不存在")
    node_ids = []
    prepared = []
    for instance in instances:
        raw_nodes = [str(node_id) for node_id in instance.get("node_ids") or [] if node_id not in (None, "")]
        if len(raw_nodes) != 1:
            return _rejected("每个采集实例必须关联一个节点")
        node_ids.append(raw_nodes[0])
        prepared.append({key: value for key, value in instance.items() if key != "group_ids"})
    owned = set(NodeOrganization.objects.filter(organization__in=ids, node_id__in=node_ids).values_list("node_id", flat=True))
    if set(node_ids) - owned:
        return _rejected("节点不存在")
    for instance in prepared:
        instance["group_ids"] = ids
    payload = {"collect_type_id": collect_type_id, "instances": prepared, "configs": configs or []}
    collect_type = CollectType.objects.filter(id=collect_type_id).first()
    payload["collector"] = collect_type.collector
    payload["collect_type"] = collect_type.name

    def action():
        CollectTypeService.batch_create_collect_configs(payload)
        return {"instance_ids": [instance.get("instance_id") for instance in prepared]}

    return _run(action, "日志采集创建失败")


def update_collect_config(*, team, instance_id, collect_type_id, child=None, base=None):
    from apps.log.models import CollectConfig
    from apps.log.services.collect_type import CollectTypeService

    ids = team_ids(team)
    instance = _owned_collect_instance(instance_id, ids)
    if instance is None or instance.collect_type_id != collect_type_id:
        return _rejected("采集实例不存在")
    for config in (child, base):
        if not config or not config.get("id"):
            continue
        row = CollectConfig.objects.filter(id=config["id"], collect_instance_id=instance.id).first()
        if row is None:
            return _rejected("采集配置不存在")

    def action():
        CollectTypeService.update_instance_config_v2(child, base, instance.id, collect_type_id)
        return {"instance_id": instance.id}

    return _run(action, "日志采集配置更新失败")


def delete_collect_instances(*, team, instance_ids):
    from django.db import transaction

    from apps.log.models import CollectConfig, CollectInstance, LogExtractor
    from apps.log.services.log_extractor.publication import mark_dirty
    from apps.rpc.node_mgmt import NodeMgmt

    ids = team_ids(team)
    requested = list(dict.fromkeys(instance_ids))
    owned = list(CollectInstance.objects.filter(id__in=requested, collectinstanceorganization__organization__in=ids).distinct())
    if len(owned) != len(requested):
        return _rejected("采集实例不存在")
    owned_ids = [instance.id for instance in owned]

    def action():
        config_objs = list(CollectConfig.objects.filter(collect_instance_id__in=owned_ids))
        child_configs = [config.id for config in config_objs if config.is_child]
        configs = [config.id for config in config_objs if not config.is_child]
        if child_configs:
            NodeMgmt().delete_child_configs(child_configs)
        if configs:
            NodeMgmt().delete_configs(configs)
        with transaction.atomic():
            list(CollectInstance.objects.select_for_update().filter(id__in=owned_ids).order_by("id").values_list("id", flat=True))
            has_extractors = LogExtractor.objects.filter(collect_instance_id__in=owned_ids).exists()
            CollectConfig.objects.filter(collect_instance_id__in=owned_ids).delete()
            CollectInstance.objects.filter(id__in=owned_ids).delete()
            if has_extractors:
                mark_dirty()
        return {"instance_ids": owned_ids}

    return _run(action, "日志采集实例移除失败")


def create_k8s_collector(*, team, collect_type_id, name, instance_id=None):
    from apps.log.services.k8s_collect import K8sLogCollectService

    ids = team_ids(team)
    if not ids:
        return _rejected("采集类型不存在")

    def action():
        return K8sLogCollectService.create_k8s_collect_instance(
            {
                "collect_type_id": collect_type_id,
                "name": name,
                "id": instance_id or name,
                "organizations": ids,
            }
        )

    return _run(action, "日志 Kubernetes 采集实例创建失败")


def save_k8s_setting(*, team, instance_id, **setting):
    from apps.log.services.k8s_collect import K8sLogCollectService

    if _owned_collect_instance(instance_id, team_ids(team)) is None:
        return _rejected("采集实例不存在")

    def action():
        saved = K8sLogCollectService.save_setting(instance_id, setting)
        return {key: value for key, value in saved.items() if key != "command"}

    return _run(action, "日志采集范围保存失败")


def k8s_install_command(*, team, instance_id, cloud_region_id, image_registry_prefix=None, tolerations=None):
    from apps.core.utils.k8s_daemonset_tolerations import TOLERATIONS_UNSET
    from apps.log.services.k8s_collect import K8sLogCollectService

    instance = _owned_collect_instance(instance_id, team_ids(team))
    if instance is None:
        return _rejected("采集实例不存在")

    def action():
        if tolerations is not None and tolerations is not TOLERATIONS_UNSET:
            K8sLogCollectService.persist_tolerations(instance.id, tolerations)
        command = K8sLogCollectService.generate_install_command(instance.id, cloud_region_id, image_registry_prefix)
        return {"install_command": command}

    return _run(action, "安装命令生成失败")


def k8s_status(*, team, instance_id):
    from apps.log.services.k8s_collect import K8sLogCollectService

    instance = _owned_collect_instance(instance_id, team_ids(team))
    if instance is None:
        return _rejected("采集实例不存在")

    def action():
        reported = K8sLogCollectService.check_collect_status(instance.id)
        return {"status": "success" if reported else "pending"}

    return _run(action, "采集状态查询失败")


def _owned_collect_instance(instance_id, ids):
    from apps.log.models import CollectInstance

    if not ids:
        return None
    return (
        CollectInstance.objects.filter(id=instance_id, collectinstanceorganization__organization__in=ids)
        .distinct()
        .first()
    )


def _collect_type_page(queryset, page, page_size):
    total = queryset.count()
    start = (page - 1) * page_size
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [_collect_type_item(row) for row in queryset[start : start + page_size]],
    }


def _collect_type_item(row):
    return {
        "id": row.id,
        "name": row.name,
        "collector": row.collector,
        "description": row.description or "",
        "display_category": row.display_category,
        "fields": row.attrs or [],
    }
