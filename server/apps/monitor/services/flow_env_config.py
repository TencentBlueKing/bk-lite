import json

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import CollectConfig, MonitorInstance, MonitorPlugin
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.utils.config_format import ConfigFormat
from apps.monitor.utils.dimension import normalize_instance_identity
from apps.monitor.utils.plugin_controller import Controller


class FlowEnvConfigService:
    ENV_KEY = "FLOW_ASSET_MAP_JSON"
    SUPPORTED_PROTOCOLS = ("netflow", "sflow")

    @classmethod
    def build_asset_map(cls, *, cloud_region_id):
        queryset = (
            MonitorInstance.objects.filter(cloud_region_id=cloud_region_id, is_deleted=False)
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
            config_payload = InstanceConfigService.get_config_content([config_obj.id])
            config_info = config_payload.get("child" if config_obj.is_child else "base")
            if not config_info:
                continue
            refreshed_info = cls._refresh_config_info(
                config_obj=config_obj,
                config_info=config_info,
                env_patch=env_patch,
            )
            InstanceConfigService.update_instance_config(
                refreshed_info if config_obj.is_child else None,
                refreshed_info if not config_obj.is_child else None,
            )

        return len(config_objs)

    @classmethod
    def _refresh_config_info(cls, *, config_obj, config_info, env_patch):
        controller = Controller(
            {
                "collector": config_obj.collector,
                "collect_type": config_obj.collect_type,
                "monitor_plugin_id": config_obj.monitor_plugin_id,
            }
        )
        template = cls._get_template(controller=controller, config_obj=config_obj)
        render_context = cls._build_render_context(
            config_obj=config_obj,
            config_info=config_info,
            env_patch=env_patch,
        )
        plugin_template_id = cls._get_plugin_template_id(config_obj.monitor_plugin_id)
        rendered_content = controller.render_template(
            template["content"],
            {
                **render_context,
                "config_id": config_info["id"].upper(),
                "plugin_id": plugin_template_id or config_obj.monitor_plugin_id,
                "monitor_plugin_id": config_obj.monitor_plugin_id,
            },
        )
        return {
            **config_info,
            "content": cls._parse_rendered_content(rendered_content, template["file_type"]),
            "env_config": cls._merge_env_config(
                existing_env_config=config_info.get("env_config"),
                env_patch=env_patch,
                config_id=config_info["id"],
                is_child=config_obj.is_child,
            ),
        }

    @classmethod
    def _get_template(cls, *, controller, config_obj):
        templates = controller.get_templates_by_collector(config_obj.collector, config_obj.collect_type).get(
            config_obj.config_type,
            [],
        )
        for template in templates:
            if config_obj.is_child and template["config_type"] == "child":
                return template
            if not config_obj.is_child and template["config_type"] != "child":
                return template
        raise BaseAppException(
            f"未找到采集模板：collector={config_obj.collector}, collect_type={config_obj.collect_type}, type={config_obj.config_type}"
        )

    @staticmethod
    def _get_plugin_template_id(monitor_plugin_id):
        if not monitor_plugin_id:
            return None
        plugin_obj = MonitorPlugin.objects.filter(id=monitor_plugin_id).only("template_id").first()
        return plugin_obj.template_id if plugin_obj else None

    @staticmethod
    def _build_render_context(*, config_obj, config_info, env_patch):
        content = config_info.get("content") or {}
        return {
            **config_info,
            **content,
            **(content.get("config") or {}),
            **normalize_instance_identity(config_obj.monitor_instance_id),
            "type": config_obj.config_type,
            "instance_type": config_obj.monitor_instance.monitor_object.name.lower(),
            **env_patch,
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

    @staticmethod
    def _parse_rendered_content(rendered_content, file_type):
        if file_type == "toml":
            return ConfigFormat.toml_to_dict(rendered_content)
        if file_type == "yaml":
            return ConfigFormat.yaml_to_dict(rendered_content)
        raise BaseAppException("file_type must be toml or yaml")
