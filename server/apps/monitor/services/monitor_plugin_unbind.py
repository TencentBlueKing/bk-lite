"""按采集模板解绑监控实例上的一份已配置插件。

只删除该插件的 CollectConfig，并同步删除 Node 上对应的子配置/基础配置。
不删除 MonitorInstance，不通知 CMDB，也不走整实例移除。
"""

from dataclasses import dataclass

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig, Metric, MonitorInstance, MonitorPlugin, MonitorPolicy, PolicyGroupRule, PolicyInstanceBaseline
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.monitor.services.policy_source_cleanup import PolicySourceCleanupService
from apps.monitor.tasks.utils.policy_multi import query_metric_items
from apps.rpc.node_mgmt import NodeMgmt

_LOG_ID_LIMIT = 200
_LAST_TEMPLATE_MESSAGE = "该实例只剩一个采集模板，请移除整个监控实例"
_NOT_BOUND_MESSAGE = "该实例未绑定此采集模板"


@dataclass(frozen=True)
class UnbindResult:
    instance_id: str
    monitor_plugin_id: int
    deleted_config_ids: tuple[str, ...]
    trimmed_policy_ids: tuple[int, ...]
    closed_alert_count: int


class MonitorPluginUnbindService:
    @classmethod
    def unbind(cls, instance_id, monitor_plugin_id, *, operator: str = "system") -> UnbindResult:
        normalized_instance_id = cls._normalize_instance_id(instance_id)
        plugin_id = cls._normalize_plugin_id(monitor_plugin_id)
        stage = {"name": "load"}
        try:
            result = cls._unbind(normalized_instance_id, plugin_id, operator=operator, stage=stage)
        except BaseAppException:
            raise
        except Exception as exc:
            logger.exception(
                "event=monitor_plugin_unbind_failed instance_id=%s monitor_plugin_id=%s failed_stage=%s error_type=%s",
                _log_token(normalized_instance_id),
                plugin_id,
                stage["name"],
                type(exc).__name__,
            )
            raise BaseAppException("解绑采集模板失败，请稍后重试", log=False) from exc

        logger.info(
            "event=monitor_plugin_unbound instance_id=%s monitor_plugin_id=%s deleted_config_count=%s trimmed_policy_count=%s closed_alert_count=%s",
            _log_token(result.instance_id),
            result.monitor_plugin_id,
            len(result.deleted_config_ids),
            len(result.trimmed_policy_ids),
            result.closed_alert_count,
        )
        return result

    @classmethod
    def _unbind(cls, instance_id: str, plugin_id: int, *, operator: str, stage: dict) -> UnbindResult:
        with transaction.atomic():
            instance = MonitorInstance.objects.select_for_update().filter(id=instance_id).first()
            if instance is None:
                raise BaseAppException("监控实例不存在")
            plugin = MonitorPlugin.objects.filter(id=plugin_id).first()
            if plugin is None:
                raise BaseAppException("采集模板不存在")

            config_rows = list(CollectConfig.objects.select_for_update().filter(monitor_instance_id=instance_id).order_by("id"))
            configured_plugin_ids = {row.monitor_plugin_id for row in config_rows if row.monitor_plugin_id}
            plugin_configs = [row for row in config_rows if row.monitor_plugin_id == plugin_id]
            if plugin_id not in configured_plugin_ids:
                raise BaseAppException(_NOT_BOUND_MESSAGE)
            if len(configured_plugin_ids) <= 1:
                raise BaseAppException(_LAST_TEMPLATE_MESSAGE)

            remaining_plugin_ids = configured_plugin_ids - {plugin_id}
            stage["name"] = "trim_policies"
            trim_policy_ids = cls._policies_to_trim(instance, plugin, remaining_plugin_ids)

            child_config_ids = [row.id for row in plugin_configs if row.is_child]
            base_config_ids = [row.id for row in plugin_configs if not row.is_child]
            stage["name"] = "delete_node_configs"
            node_mgmt = NodeMgmt()
            if child_config_ids:
                node_mgmt.delete_child_configs(child_config_ids)
            if base_config_ids:
                node_mgmt.delete_configs(base_config_ids)

            deleted_config_ids = tuple(row.id for row in plugin_configs)
            stage["name"] = "delete_collect_config"
            CollectConfig.objects.filter(id__in=deleted_config_ids).delete()

            stage["name"] = "trim_policies"
            disabled_policy_ids = cls._trim_policy_sources(trim_policy_ids, instance_id)
            if disabled_policy_ids:
                PolicySourceCleanupService._disable_periodic_tasks(disabled_policy_ids)
            if trim_policy_ids:
                PolicyInstanceBaseline.objects.filter(
                    policy_id__in=trim_policy_ids,
                    monitor_instance_id=instance_id,
                ).delete()
            closed_alert_count = MonitorInstanceRemovalService.close_alerts_for_instances(
                (instance_id,),
                operator=operator,
                reason="plugin_unbound",
                policy_ids=trim_policy_ids,
            )

        return UnbindResult(
            instance_id=instance_id,
            monitor_plugin_id=plugin_id,
            deleted_config_ids=deleted_config_ids,
            trimmed_policy_ids=tuple(trim_policy_ids),
            closed_alert_count=closed_alert_count,
        )

    @classmethod
    def _policies_to_trim(cls, instance, plugin, remaining_plugin_ids) -> list[int]:
        policies = list(MonitorPolicy.objects.filter(monitor_object_id=instance.monitor_object_id).select_related("source_template"))
        if not policies:
            return []

        pinned_policy_ids = set(
            PolicyGroupRule.objects.filter(
                plugin_id=plugin.id,
                policy_id__in=[policy.id for policy in policies],
            ).values_list("policy_id", flat=True)
        )
        metric_rows = Metric.objects.filter(monitor_object_id=instance.monitor_object_id).values(
            "id",
            "name",
            "monitor_plugin_id",
        )
        metrics_by_id = {}
        producers_by_name = {}
        for row in metric_rows:
            metrics_by_id[row["id"]] = row
            name = str(row["name"] or "").strip()
            if not name or not row["monitor_plugin_id"]:
                continue
            producers_by_name.setdefault(name, set()).add(row["monitor_plugin_id"])

        trimmed = []
        for policy in policies:
            if not _source_contains(policy.source, instance.id):
                continue
            names = _policy_metric_names(policy, metrics_by_id)
            if not _explicitly_bound(policy, plugin, pinned_policy_ids, metrics_by_id, producers_by_name):
                continue
            if _shared_with_remaining(names, remaining_plugin_ids, producers_by_name):
                continue
            trimmed.append(policy.id)
        return trimmed

    @staticmethod
    def _trim_policy_sources(policy_ids, instance_id) -> list[int]:
        if not policy_ids:
            return []
        disabled_ids = []
        locked_policies = list(MonitorPolicy.objects.select_for_update().filter(id__in=policy_ids).order_by("id"))
        for policy in locked_policies:
            source = policy.source if isinstance(policy.source, dict) else {}
            if source.get("type") != "instance":
                continue
            old_values = list(source.get("values") or [])
            new_values = [value for value in old_values if str(value) != str(instance_id)]
            if new_values == old_values:
                continue
            policy.source = {"type": "instance", "values": new_values}
            update_fields = ["source", "updated_at"]
            if not new_values and policy.enable:
                policy.enable = False
                update_fields.append("enable")
                disabled_ids.append(policy.id)
            policy.save(update_fields=update_fields)
        return disabled_ids

    @staticmethod
    def _normalize_instance_id(instance_id) -> str:
        if instance_id in (None, ""):
            raise BaseAppException("instance_id 不能为空")
        text = str(instance_id).strip()
        if not text:
            raise BaseAppException("instance_id 不能为空")
        return text

    @staticmethod
    def _normalize_plugin_id(monitor_plugin_id) -> int:
        if isinstance(monitor_plugin_id, bool) or monitor_plugin_id in (None, ""):
            raise BaseAppException("monitor_plugin_id 无效")
        try:
            plugin_id = int(monitor_plugin_id)
        except (TypeError, ValueError):
            raise BaseAppException("monitor_plugin_id 无效") from None
        if plugin_id <= 0:
            raise BaseAppException("monitor_plugin_id 无效")
        return plugin_id


def _source_contains(source, instance_id) -> bool:
    if not isinstance(source, dict) or source.get("type") != "instance":
        return False
    target = str(instance_id)
    return any(str(value) == target for value in source.get("values") or [])


def _policy_metric_names(policy, metrics_by_id) -> list[str]:
    names = []
    for item in query_metric_items(policy.query_condition or {}):
        if not isinstance(item, dict):
            continue
        name = str(item.get("metric_name") or "").strip()
        metric_id = item.get("metric_id")
        if not name and metric_id in metrics_by_id:
            name = str(metrics_by_id[metric_id]["name"] or "").strip()
        if name:
            names.append(name)
    return names


def _explicitly_bound(policy, plugin, pinned_policy_ids, metrics_by_id, producers_by_name) -> bool:
    if policy.id in pinned_policy_ids:
        return True
    template = policy.source_template
    if template is not None and template.plugin_id == plugin.id:
        return True
    items = [item for item in query_metric_items(policy.query_condition or {}) if isinstance(item, dict)]
    if not items:
        return False
    metric_ids = [item.get("metric_id") for item in items if item.get("metric_id")]
    if len(metric_ids) == len(items):
        owners = set()
        for metric_id in metric_ids:
            row = metrics_by_id.get(metric_id)
            if row is None:
                return False
            owners.add(row["monitor_plugin_id"])
        return owners == {plugin.id}
    plugin_names = [str(item.get("metric_plugin") or "").strip() for item in items]
    if all(plugin_names) and set(plugin_names) == {plugin.name}:
        return True
    names = _policy_metric_names(policy, metrics_by_id)
    if not names:
        return False
    return all(producers_by_name.get(name) == {plugin.id} for name in names)


def _shared_with_remaining(names, remaining_plugin_ids, producers_by_name) -> bool:
    if not names or not remaining_plugin_ids:
        return False
    remaining = set(remaining_plugin_ids)
    return any(producers_by_name.get(name, set()) & remaining for name in names)


def _log_token(value) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    if len(text) <= _LOG_ID_LIMIT:
        return text
    return text[:_LOG_ID_LIMIT]
