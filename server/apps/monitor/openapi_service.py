"""监控 OpenAPI。组织集合只接受网关注入，不读请求里的组织字段。"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.k8s_daemonset_tolerations import TOLERATIONS_UNSET
from apps.monitor.filters.monitor_policy import exclude_policy_group_rules
from apps.monitor.models import (
    Metric,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorPlugin,
    MonitorPluginUITemplate,
    MonitorPolicy,
    PolicyGroup,
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyOrganization,
)
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, _build_query
from apps.monitor.services.k3s_onboarding import K3SOnboardingService
from apps.monitor.services.manual_collect import ManualCollectService
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.monitor.services.metrics import Metrics, MetricsQueryBudgetExceeded
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.node_mgmt.models import NodeOrganization

METRIC_RANGE_WINDOW = timedelta(hours=6)


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


def page_result(queryset, page, page_size, serialize):
    total = queryset.count()
    start = (page - 1) * page_size
    rows = list(queryset[start : start + page_size])
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [serialize(row) for row in rows],
    }


def list_objects(*, team, page, page_size, keyword):
    if not team_ids(team):
        return page_result(MonitorObject.objects.none(), page, page_size, _object_item)
    queryset = MonitorObject.objects.filter(is_visible=True).order_by("order", "id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(display_name__icontains=keyword))
    return page_result(queryset, page, page_size, _object_item)


def list_instances(*, team, page, page_size, keyword, monitor_object_id=None):
    ids = team_ids(team)
    if not ids:
        return page_result(MonitorInstance.objects.none(), page, page_size, _instance_item)
    queryset = (
        MonitorInstance.objects.filter(is_deleted=False, monitorinstanceorganization__organization__in=ids)
        .distinct()
        .order_by("id")
    )
    if monitor_object_id:
        queryset = queryset.filter(monitor_object_id=monitor_object_id)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(ip__icontains=keyword))
    return page_result(queryset, page, page_size, _instance_item)


def list_policies(*, team, page, page_size, keyword, monitor_object_id=None):
    ids = team_ids(team)
    if not ids:
        return page_result(MonitorPolicy.objects.none(), page, page_size, _policy_item)
    owned = PolicyOrganization.objects.filter(organization__in=ids).values("policy_id")
    queryset = exclude_policy_group_rules(MonitorPolicy.objects.filter(id__in=owned)).order_by("id")
    if monitor_object_id:
        queryset = queryset.filter(monitor_object_id=monitor_object_id)
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    return page_result(queryset, page, page_size, _policy_item)


def _object_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "display_name": obj.display_name,
        "type": obj.type_id,
        "level": obj.level,
        "parent_id": obj.parent_id,
        "description": obj.description,
    }


def _instance_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "monitor_object_id": obj.monitor_object_id,
        "ip": obj.ip,
        "is_active": obj.is_active,
        "node_id": obj.node_id,
        "cmdb_id": obj.cmdb_id,
        "cloud_region_id": obj.cloud_region_id,
    }


def _policy_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "monitor_object_id": obj.monitor_object_id,
        "alert_name": obj.alert_name,
        "enable": obj.enable,
        "collect_type": obj.collect_type,
    }


def list_metrics(*, team, page, page_size, keyword, monitor_object_id):
    if not team_ids(team):
        return page_result(Metric.objects.none(), page, page_size, _metric_item)
    if not MonitorObject.objects.filter(id=monitor_object_id, is_visible=True).exists():
        return {"result": False, "message": "监控对象不存在"}
    queryset = Metric.objects.filter(monitor_object_id=monitor_object_id).order_by("sort_order", "id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(display_name__icontains=keyword))
    return page_result(queryset, page, page_size, _metric_item)


def query_metric_instant(*, team, instance_id, metric_id):
    prepared = _prepare_metric_query(team, instance_id, metric_id)
    if prepared.get("result") is False:
        return prepared
    try:
        query, _applied = Metrics.apply_card_series_limit(prepared["query"])
        payload = Metrics.get_metrics(query)
    except (AuthorizedMetricQueryError, MetricsQueryBudgetExceeded) as exc:
        return {"result": False, "message": str(exc)}
    except Exception:
        return {"result": False, "message": "指标查询失败"}
    projected = _project_metric_payload(payload, ranged=False)
    if projected.get("result") is False:
        return projected
    return {
        "metric_id": prepared["metric"].id,
        "instance_id": prepared["instance"].id,
        "unit": prepared["metric"].unit,
        **projected,
    }


def query_metric_range(*, team, instance_id, metric_id, start, end, step="5m"):
    start, end = _aware(start), _aware(end)
    if end <= start:
        return {"result": False, "message": "开始时间必须早于结束时间"}
    if end - start > METRIC_RANGE_WINDOW:
        return {"result": False, "message": "查询时间范围不能超过 6 小时"}
    try:
        Metrics.parse_step_to_seconds(step)
    except ValueError:
        return {"result": False, "message": "查询步长无效"}
    prepared = _prepare_metric_query(team, instance_id, metric_id)
    if prepared.get("result") is False:
        return prepared
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    try:
        payload = Metrics.get_metrics_range(
            prepared["query"],
            start_ms,
            end_ms,
            step,
            card_budget=True,
        )
    except (AuthorizedMetricQueryError, MetricsQueryBudgetExceeded) as exc:
        return {"result": False, "message": str(exc)}
    except Exception:
        return {"result": False, "message": "指标查询失败"}
    projected = _project_metric_payload(payload, ranged=True)
    if projected.get("result") is False:
        return projected
    return {
        "metric_id": prepared["metric"].id,
        "instance_id": prepared["instance"].id,
        "unit": prepared["metric"].unit,
        "start": start.isoformat(),
        "end": end.isoformat(),
        **projected,
    }


def _prepare_metric_query(team, instance_id, metric_id):
    ids = team_ids(team)
    instance = (
        MonitorInstance.objects.filter(
            id=instance_id,
            is_deleted=False,
            monitorinstanceorganization__organization__in=ids,
        )
        .distinct()
        .first()
        if ids
        else None
    )
    if instance is None:
        return {"result": False, "message": "监控实例不存在"}
    metric = Metric.objects.filter(id=metric_id, monitor_object_id=instance.monitor_object_id).first()
    if metric is None:
        return {"result": False, "message": "监控指标不存在"}
    try:
        query = _build_query(metric, (instance.id,), None, "AVG")
    except AuthorizedMetricQueryError as exc:
        return {"result": False, "message": str(exc)}
    return {"metric": metric, "instance": instance, "query": query}


def _project_metric_payload(payload, *, ranged):
    if not isinstance(payload, dict) or payload.get("status") not in (None, "success"):
        return {"result": False, "message": "指标查询失败"}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    series = []
    for item in data.get("result") or []:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric") if isinstance(item.get("metric"), dict) else {}
        clean = {str(key): value for key, value in labels.items() if not str(key).startswith("__")}
        if ranged:
            points = [
                {"timestamp": pair[0], "value": pair[1]}
                for pair in item.get("values") or []
                if isinstance(pair, (list, tuple)) and len(pair) >= 2
            ]
            series.append({"labels": clean, "points": points})
        else:
            value = item.get("value")
            point = None
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                point = {"timestamp": value[0], "value": value[1]}
            series.append({"labels": clean, "point": point})
    budget = data.get("series_budget") if isinstance(data.get("series_budget"), dict) else {}
    return {"series": series, "truncated": bool(budget.get("truncated"))}


def _metric_item(obj):
    names = []
    for item in obj.dimensions or []:
        raw = item.get("name") if isinstance(item, dict) else item
        if raw not in (None, ""):
            names.append(str(raw))
    return {
        "id": obj.id,
        "name": obj.name,
        "display_name": obj.display_name,
        "unit": obj.unit,
        "dimensions": names,
        "description": obj.description or "",
    }


def _aware(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.utc)
    return value


def _rejected(message):
    return {"result": False, "message": message}


def _public_message(exc, fallback):
    text = str(exc)
    lowered = text.lower()
    if "http" in lowered or "token" in lowered or "password" in lowered or "private_key" in lowered or len(text) > 200:
        return fallback
    return text or fallback


def _run(action, fallback):
    try:
        return action()
    except BaseAppException as exc:
        return _rejected(_public_message(exc, fallback))
    except Exception:
        return _rejected(fallback)


def _actor(team, user_info):
    ids = team_ids(team)
    if not ids:
        return None
    info = user_info or {}
    return {
        "username": info.get("user") or "",
        "domain": info.get("domain") or "domain.com",
        "current_team": ids[0],
        "include_children": False,
        "is_superuser": False,
        "group_list": ids,
        "data_team_ids": ids,
    }


def _visible_object(object_id):
    return MonitorObject.objects.filter(id=object_id, is_visible=True).first()


def _owned_instance(instance_id, ids):
    return (
        MonitorInstance.objects.filter(
            id=instance_id,
            is_deleted=False,
            monitorinstanceorganization__organization__in=ids,
        )
        .distinct()
        .first()
    )


def list_plugins(*, team, page, page_size, keyword, monitor_object_id):
    if not team_ids(team):
        return page_result(MonitorPlugin.objects.none(), page, page_size, _plugin_item)
    if _visible_object(monitor_object_id) is None:
        return _rejected("监控对象不存在")
    queryset = MonitorPlugin.objects.filter(monitor_object__id=monitor_object_id).distinct().order_by("id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(display_name__icontains=keyword))
    return page_result(queryset, page, page_size, _plugin_item)


def get_plugin_form(*, team, plugin_id):
    if not team_ids(team):
        return _rejected("插件不存在")
    plugin = MonitorPlugin.objects.filter(id=plugin_id, monitor_object__is_visible=True).distinct().first()
    if plugin is None:
        return _rejected("插件不存在")
    template = MonitorPluginUITemplate.objects.filter(plugin=plugin).order_by("-id").first()
    form = template.content if template is not None and isinstance(template.content, dict) else {}
    return {
        "plugin_id": plugin.id,
        "name": plugin.name,
        "display_name": plugin.display_name,
        "collect_type": plugin.collect_type,
        "collector": plugin.collector,
        "form": form,
    }


def list_policy_groups(*, team, page, page_size, keyword, monitor_object_id, plugin_id=None):
    ids = team_ids(team)
    if not ids:
        return page_result(PolicyGroup.objects.none(), page, page_size, lambda row: row)
    if _visible_object(monitor_object_id) is None:
        return _rejected("监控对象不存在")
    queryset = (
        PolicyGroup.objects.filter(organization__in=ids, monitor_object_id=monitor_object_id)
        .annotate(member_count=Count("memberships", filter=Q(memberships__state=PolicyGroupMembership.STATE_MEMBER)))
        .prefetch_related("rules__plugin", "rules__policy")
        .order_by("id")
    )
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    default_ids = set(
        PolicyGroupDefault.objects.filter(organization__in=ids, monitor_object_id=monitor_object_id).values_list("policy_group_id", flat=True)
    )

    def serialize(group):
        return _policy_group_item(group, default_ids, plugin_id)

    return page_result(queryset, page, page_size, serialize)


def create_integration(
    *,
    team,
    user_info,
    monitor_object_id,
    monitor_plugin_id,
    instances,
    configs=None,
    policy_group=None,
    credential=None,
):
    actor = _actor(team, user_info)
    if actor is None or _visible_object(monitor_object_id) is None:
        return _rejected("监控对象不存在")
    plugin = MonitorPlugin.objects.filter(id=monitor_plugin_id, monitor_object__id=monitor_object_id).first()
    if plugin is None:
        return _rejected("插件不存在")
    node_ids = []
    for instance in instances:
        for node_id in instance.get("node_ids") or []:
            if node_id not in (None, ""):
                node_ids.append(str(node_id))
    if not node_ids:
        return _rejected("实例缺少节点")
    owned = set(
        NodeOrganization.objects.filter(organization__in=actor["data_team_ids"], node_id__in=node_ids).values_list("node_id", flat=True)
    )
    if set(node_ids) - owned:
        return _rejected("节点不存在")
    choice = policy_group or {"join": False}
    if choice.get("join"):
        group = PolicyGroup.objects.filter(
            id=choice.get("group_id"),
            organization__in=actor["data_team_ids"],
            monitor_object_id=monitor_object_id,
        ).first()
        if group is None:
            return _rejected("策略组不存在")
    payload = {
        "monitor_object_id": monitor_object_id,
        "monitor_plugin_id": plugin.id,
        "collector": plugin.collector,
        "collect_type": plugin.collect_type,
        "instances": [{key: value for key, value in instance.items() if key != "group_ids"} for instance in instances],
        "configs": configs or [],
        "policy_group": {"join": bool(choice.get("join")), "group_id": choice.get("group_id")},
    }
    if credential:
        payload["credential"] = credential

    def action():
        instance_ids = InstanceConfigService.create_monitor_instance_by_node_mgmt(payload, actor)
        return {
            "instance_ids": list(instance_ids or []),
            "policy_group_results": list(getattr(instance_ids, "policy_group_results", []) or []),
        }

    return _run(action, "监控接入失败")


def delete_integrations(*, team, user_info, instance_ids):
    ids = team_ids(team)
    requested = list(dict.fromkeys(str(item) for item in instance_ids))
    if not ids:
        return _rejected("监控实例不存在")
    owned_ids = set(
        MonitorInstance.objects.filter(
            id__in=requested,
            is_deleted=False,
            monitorinstanceorganization__organization__in=ids,
        )
        .distinct()
        .values_list("id", flat=True)
    )
    if owned_ids != set(requested):
        return _rejected("监控实例不存在")
    actor = _actor(team, user_info) or {}

    def action():
        result = MonitorInstanceRemovalService.remove(
            requested,
            operator=actor.get("username") or "system",
            reason="manual_instance_deleted",
        )
        return {"instance_ids": list(result.removed_ids)}

    return _run(action, "监控实例删除失败")


def create_cluster_collector(*, team, user_info, collector_type, monitor_object_id, name, instance_id, interval=None):
    actor = _actor(team, user_info)
    if actor is None:
        return _rejected("监控对象不存在")
    organizations = actor["data_team_ids"]

    def action():
        data = {
            "monitor_object_id": monitor_object_id,
            "name": name,
            "organizations": organizations,
        }
        if interval is not None:
            data["interval"] = interval
        if collector_type == "k3s":
            data["instance_id"] = instance_id
            return K3SOnboardingService.create_instance(**data, actor_context=actor)
        data["id"] = instance_id
        return ManualCollectService.create_manual_collect_instance(data, actor_context=actor)

    return _run(action, "集群采集实例创建失败")


def cluster_install_command(
    *,
    team,
    collector_type,
    instance_id,
    cloud_region_id,
    image_registry_prefix=None,
    tolerations=None,
):
    ids = team_ids(team)
    instance = _cluster_instance(instance_id, ids)
    if instance is None:
        return _rejected("采集实例不存在")
    if collector_type == "k3s":

        def k3s_action():
            commands = K3SOnboardingService.generate_install_commands(instance_id=instance.id, cloud_region_id=cloud_region_id)
            return {
                "install_command": commands.get("install_command", ""),
                "uninstall_command": commands.get("uninstall_command", ""),
            }

        return _run(k3s_action, "安装命令生成失败")

    def kubernetes_action():
        toleration_value = tolerations if tolerations is not None else TOLERATIONS_UNSET
        if tolerations is not None:
            ManualCollectService.persist_k8s_daemonset_tolerations(instance.id, tolerations)
        command = ManualCollectService.generate_install_command(
            instance.id,
            cloud_region_id,
            image_registry_prefix,
            toleration_value,
        )
        return {"install_command": command}

    return _run(kubernetes_action, "安装命令生成失败")


def cluster_status(*, team, collector_type, instance_id, monitor_object_id=None):
    ids = team_ids(team)
    if not ids:
        return _rejected("采集实例不存在")
    if collector_type == "k3s":

        def k3s_action():
            instance = K3SOnboardingService._get_cluster_instance(instance_id)
            if not MonitorInstanceOrganization.objects.filter(monitor_instance=instance, organization__in=ids).exists():
                return _rejected("采集实例不存在")
            result = K3SOnboardingService.verify_reporting(instance_id)
            signals = {
                name: {"status": item.get("status")}
                for name, item in (result.get("signals") or {}).items()
                if isinstance(item, dict)
            }
            return {"status": result.get("status"), "signals": signals}

        return _run(k3s_action, "采集状态查询失败")

    instance = _cluster_instance(instance_id, ids)
    if instance is None or instance.monitor_object_id != monitor_object_id:
        return _rejected("采集实例不存在")

    def kubernetes_action():
        reported = ManualCollectService.check_collect_status(monitor_object_id, instance.id)
        return {"status": "success" if reported else "pending"}

    return _run(kubernetes_action, "采集状态查询失败")


def _cluster_instance(instance_id, ids):
    direct = _owned_instance(instance_id, ids)
    if direct is not None:
        return direct
    stored = _owned_instance(str((str(instance_id),)), ids)
    return stored


def _plugin_item(plugin):
    return {
        "id": plugin.id,
        "name": plugin.name,
        "display_name": plugin.display_name,
        "collect_type": plugin.collect_type,
        "collector": plugin.collector,
        "description": plugin.description or "",
    }


def _policy_group_item(group, default_ids, plugin_id):
    rules = []
    applicable = 0
    for rule in group.rules.all():
        matches = plugin_id is None or rule.plugin_id == plugin_id
        if plugin_id is not None and matches:
            applicable += 1
        item = {
            "id": rule.id,
            "name": rule.name,
            "plugin_id": rule.plugin_id,
            "plugin_name": rule.plugin.name if rule.plugin_id else "",
            "threshold": rule.policy.threshold if rule.policy_id else None,
        }
        if plugin_id is not None:
            item["applies_to_plugin"] = matches
        rules.append(item)
    payload = {
        "id": group.id,
        "name": group.name,
        "is_default": group.id in default_ids,
        "member_count": group.member_count,
        "rules": rules,
    }
    if plugin_id is not None:
        payload["has_applicable_rule"] = applicable > 0
    return payload
