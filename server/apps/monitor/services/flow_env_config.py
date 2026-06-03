import json

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig, MonitorInstance
from apps.monitor.services.node_mgmt import InstanceConfigService


class FlowEnvConfigService:
    ENV_KEY = "FLOW_ASSET_MAP_JSON"
    SUPPORTED_PROTOCOLS = ("netflow", "sflow")
    SUPPORTED_MONITOR_OBJECT_NAMES = ("Switch", "Router", "Firewall", "Loadbalance")

    @classmethod
    def build_asset_map(cls, *, cloud_region_id):
        queryset = (
            MonitorInstance.objects.filter(
                cloud_region_id=cloud_region_id,
                is_deleted=False,
                monitor_object__name__in=cls.SUPPORTED_MONITOR_OBJECT_NAMES,
            )
            .select_related("monitor_object")
            .order_by("created_at", "id")
        )
        payload = {}
        for item in queryset:
            if not item.ip or not item.enabled_protocols:
                continue
            payload[f"{item.cloud_region_id}:{item.ip}"] = {
                "instance_id": item.id,
                "instance_type": item.monitor_object.name.lower(),
                "fallback_sampling_rate": item.fallback_sampling_rate,
                "protocols": item.enabled_protocols,
            }
        return payload

    @classmethod
    def build_env_patch(cls, *, cloud_region_id):
        return {
            f"ENV_{cls.ENV_KEY}": json.dumps(
                cls.build_asset_map(cloud_region_id=cloud_region_id),
                sort_keys=True,
            )
        }

    @classmethod
    def refresh_collect_configs(cls, *, cloud_region_id):
        env_patch = cls.build_env_patch(cloud_region_id=cloud_region_id)
        config_objs = list(
            CollectConfig.objects.filter(
                collect_type__in=cls.SUPPORTED_PROTOCOLS,
                monitor_instance__cloud_region_id=cloud_region_id,
            )
            .select_related("monitor_instance__monitor_object", "monitor_plugin")
            .order_by("id")
        )

        for config_obj in config_objs:
            try:
                config_payload = InstanceConfigService.get_config_content([config_obj.id])
                config_info = config_payload.get("child" if config_obj.is_child else "base")
                if not config_info:
                    continue
                refreshed_info = cls._merge_config_env(
                    config_info=config_info,
                    env_patch=env_patch,
                    config_id=config_obj.id,
                    is_child=config_obj.is_child,
                )
                InstanceConfigService.update_instance_config(
                    refreshed_info if config_obj.is_child else None,
                    refreshed_info if not config_obj.is_child else None,
                )
            except Exception:
                logger.exception("刷新 Flow env_config 失败: config_id=%s", config_obj.id)

        return len(config_objs)

    @classmethod
    def _merge_config_env(cls, *, config_info, env_patch, config_id, is_child):
        return {
            **config_info,
            "env_config": cls._merge_env_config(
                existing_env_config=config_info.get("env_config"),
                env_patch=env_patch,
                config_id=config_id,
                is_child=is_child,
            ),
        }

    @classmethod
    def _merge_env_config(cls, *, existing_env_config, env_patch, config_id, is_child):
        env_config = {
            key[4:]: value
            for key, value in env_patch.items()
            if key.startswith("ENV_")
        }
        if is_child:
            env_config = {f"{key.upper()}__{config_id.upper()}": value for key, value in env_config.items()}
        return {
            **(existing_env_config or {}),
            **env_config,
        }
