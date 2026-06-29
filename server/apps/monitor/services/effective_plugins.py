from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.models import CollectConfig, MonitorObject, MonitorPlugin
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class MonitorEffectivePluginService:
    @staticmethod
    def get_effective_plugins(monitor_object_id: int, instance_id: str, locale: str = "zh-Hans") -> list[dict]:
        monitor_object = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_object:
            raise BaseAppException("Monitor object does not exist")

        # Note: we intentionally do not require a MonitorInstance row here.
        # Derived / auto-discovered instances (e.g. K8s Pod and Node) report
        # metrics under an instance_id that has no MonitorInstance row of its
        # own. Their effective plugins are still fully resolvable from reported
        # metrics and collect configs (both keyed by instance_id only), so
        # requiring a row would 500 the detail view of every derived instance.
        # A bogus instance_id simply yields no configured/reported plugins below
        # and returns an empty list.

        plugins = list(MonitorPlugin.objects.filter(monitor_object=monitor_object).distinct())
        if not plugins:
            return []

        configured_plugin_ids = MonitorEffectivePluginService._get_configured_plugin_ids(instance_id)
        reported_plugin_ids = MonitorEffectivePluginService._get_reported_plugin_ids(
            plugins,
            instance_id,
            MonitorEffectivePluginService._get_instance_id_keys(monitor_object),
        )
        effective_plugin_ids = configured_plugin_ids | reported_plugin_ids
        if not effective_plugin_ids:
            return []

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=locale)
        data = []
        for plugin in plugins:
            if plugin.id not in effective_plugin_ids:
                continue

            is_configured = plugin.id in configured_plugin_ids
            is_reported = plugin.id in reported_plugin_ids
            item = MonitorEffectivePluginService._serialize_plugin(plugin, lan)
            item.update(
                status=PluginConstants.STATUS_NORMAL if is_reported else PluginConstants.STATUS_OFFLINE,
                collect_mode=PluginConstants.COLLECT_MODE_AUTO if is_configured else PluginConstants.COLLECT_MODE_MANUAL,
                configured=is_configured,
                config_source=MonitorEffectivePluginService._get_config_source(is_configured, is_reported),
            )
            data.append(item)

        data.sort(key=MonitorEffectivePluginService._sort_key)
        return data

    @staticmethod
    def _get_configured_plugin_ids(instance_id: str) -> set[int]:
        return set(
            CollectConfig.objects.filter(
                monitor_instance_id=instance_id,
                monitor_plugin_id__isnull=False,
            ).values_list("monitor_plugin_id", flat=True)
        )

    @staticmethod
    def _get_reported_plugin_ids(plugins: list[MonitorPlugin], instance_id: str, instance_id_keys: list[str]) -> set[int]:
        reported_plugin_ids = set()
        # 主键(instance_id 维度的首键)值,用于多键对象的退化匹配。
        parsed = parse_instance_id(instance_id)
        primary_key = instance_id_keys[0] if instance_id_keys else "instance_id"
        target_primary = str(parsed[0]) if parsed else None
        vm_api = VictoriaMetricsAPI()
        for plugin in plugins:
            query = (plugin.status_query or "").strip()
            if not query:
                continue
            try:
                response = vm_api.query(query, step="20m")
            except Exception:
                logger.exception("Failed to query monitor plugin status. plugin_id=%s instance_id=%s", plugin.id, instance_id)
                continue

            for metric in response.get("data", {}).get("result", []):
                labels = metric.get("metric", {})
                metric_instance_id = str(tuple(labels.get(key) for key in instance_id_keys))
                # 全键精确匹配;若插件 status_query 只按主键 instance_id 分组(K8s 多键对象 Pod/Node
                # 的 K8S 插件状态查询即 `... by (instance_id)`,标签里没有 pod/node),退化为按主键匹配
                # —— 同集群下的派生 Pod/Node 视为上报该插件,否则其生效插件/全量指标会一律为空。
                if metric_instance_id == instance_id or (
                    target_primary is not None
                    and str(labels.get(primary_key)) == target_primary
                ):
                    reported_plugin_ids.add(plugin.id)
                    break
        return reported_plugin_ids

    @staticmethod
    def _get_instance_id_keys(monitor_object: MonitorObject) -> list[str]:
        keys = getattr(monitor_object, "instance_id_keys", []) or []
        normalized_keys = [str(key) for key in keys if key not in (None, "")]
        return normalized_keys or ["instance_id"]

    @staticmethod
    def _serialize_plugin(plugin: MonitorPlugin, lan: LanguageLoader) -> dict:
        is_custom = plugin.template_type in {"api", "pull", "snmp"}
        if is_custom:
            display_name = plugin.display_name or plugin.name
            display_description = plugin.description
        else:
            plugin_key = f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{plugin.name}"
            display_name = lan.get(f"{plugin_key}.name") or plugin.display_name or plugin.name
            display_description = lan.get(f"{plugin_key}.desc") or plugin.description

        return {
            "id": plugin.id,
            "name": plugin.name,
            "display_name": display_name,
            "display_description": display_description,
            "template_id": plugin.template_id,
            "template_type": plugin.template_type,
            "collector": plugin.collector,
            "collect_type": plugin.collect_type,
            "is_pre": plugin.is_pre,
            "is_custom": is_custom,
        }

    @staticmethod
    def _get_config_source(is_configured: bool, is_reported: bool) -> str:
        if is_configured and is_reported:
            return PluginConstants.CONFIG_SOURCE_CONFIGURED_REPORTED
        if is_configured:
            return PluginConstants.CONFIG_SOURCE_CONFIGURED
        return PluginConstants.CONFIG_SOURCE_REPORTED_ONLY

    @staticmethod
    def _sort_key(item: dict):
        if item.get("is_pre"):
            category = 0
        elif not item.get("is_custom"):
            category = 1
        else:
            category = 2
        return category, item.get("id") or 0
