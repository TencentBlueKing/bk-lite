import json

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import MonitorInstance
from apps.monitor.utils.dimension import parse_instance_id
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import CollectorConfiguration


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
                "instance_id": parse_instance_id(item.id)[0],
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
        config_objs = cls._get_region_receiver_base_configs(cloud_region_id=cloud_region_id)
        if not config_objs:
            logger.info("未找到可刷新的 Flow Telegraf 基础配置: cloud_region_id=%s", cloud_region_id)
            return 0

        for config_obj in config_objs:
            try:
                config_obj.env_config = cls._merge_env_config(
                    existing_env_config=config_obj.env_config,
                    env_patch=env_patch,
                )
                config_obj.save(update_fields=["env_config"])
            except Exception:
                logger.exception("刷新 Flow Telegraf 基础配置 env_config 失败: config_id=%s", config_obj.id)

        return len(config_objs)

    @classmethod
    def _get_region_receiver_base_configs(cls, *, cloud_region_id):
        return list(
            CollectorConfiguration.objects.filter(
                cloud_region_id=cloud_region_id,
                collector__name="Telegraf",
                is_pre=True,
                nodes__cloud_region_id=cloud_region_id,
                nodes__node_type=ControllerConstants.NODE_TYPE_CONTAINER,
            )
            .distinct()
            .order_by("id")
        )

    @classmethod
    def _merge_env_config(cls, *, existing_env_config, env_patch):
        env_config = {
            key[4:]: value
            for key, value in env_patch.items()
            if key.startswith("ENV_")
        }
        return {
            **(existing_env_config or {}),
            **env_config,
        }
