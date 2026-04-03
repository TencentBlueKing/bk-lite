from urllib.parse import urlsplit, urlunsplit

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import Metric, MonitorObject, MonitorPlugin
from apps.rpc.node_mgmt import NodeMgmt


DEFAULT_TELEGRAF_HTTP_LISTENER_PORT = 19090
DEFAULT_TELEGRAF_HTTP_LISTENER_PATH = "/telegraf/api"


class TemplateAccessGuideService:
    DEFAULT_TIMESTAMP_MS_EXAMPLE = 1712052000000

    @staticmethod
    def resolve_required_int(value, field_name: str) -> int:
        if value in (None, ""):
            raise BaseAppException(f"{field_name}不能为空")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise BaseAppException(f"{field_name}不合法") from exc

    @staticmethod
    def get_telegraf_listener_endpoint(cloud_region_id: int) -> str:
        env_config = NodeMgmt().get_cloud_region_envconfig(cloud_region_id)
        if not isinstance(env_config, dict):
            raise BaseAppException("获取云区域环境变量失败")

        endpoint = env_config.get("TELEGRAF_HTTP_LISTENER_URL")
        if endpoint:
            path = DEFAULT_TELEGRAF_HTTP_LISTENER_PATH
            parts = urlsplit(endpoint)
            if parts.scheme and parts.netloc:
                normalized_path = path if path.startswith("/") else f"/{path}"
                return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))
            return endpoint

        node_server_url = env_config.get("NODE_SERVER_URL")
        if not node_server_url:
            raise BaseAppException("当前云区域未配置 NODE_SERVER_URL，无法拼接 Telegraf 接入地址")

        parts = urlsplit(node_server_url)
        if not parts.hostname:
            raise BaseAppException("NODE_SERVER_URL 配置不合法，无法拼接 Telegraf 接入地址")

        scheme = parts.scheme or "http"
        return urlunsplit(
            (
                scheme,
                f"{parts.hostname}:{DEFAULT_TELEGRAF_HTTP_LISTENER_PORT}",
                DEFAULT_TELEGRAF_HTTP_LISTENER_PATH,
                "",
                "",
            )
        )

    @staticmethod
    def get_template_document(
        plugin: MonitorPlugin,
        organization_id: int,
        cloud_region_id: int,
    ):
        monitor_object_ids = list(plugin.monitor_object.values_list("id", flat=True))
        monitor_object = MonitorObject._default_manager.filter(id__in=monitor_object_ids).order_by("id").first()
        if not monitor_object:
            raise BaseAppException("模板未绑定监控对象")

        metrics = list(
            Metric._default_manager.filter(monitor_plugin=plugin)
            .order_by("sort_order", "id")
            .values("name", "display_name", "description", "unit", "data_type", "dimensions")
        )
        endpoint = TemplateAccessGuideService.get_telegraf_listener_endpoint(cloud_region_id)

        metric_name = metrics[0]["name"] if metrics else "demo_metric"
        line_without_timestamp = (
            f"{metric_name},organization_id={organization_id},instance_type={monitor_object.name},plugin_id={getattr(plugin, 'pk', None)} value=1"
        )
        line_with_timestamp_ms = f"{line_without_timestamp} {TemplateAccessGuideService.DEFAULT_TIMESTAMP_MS_EXAMPLE}"

        return {
            "template_id": plugin.template_id,
            "display_name": plugin.display_name or plugin.name,
            "plugin_id": getattr(plugin, "pk", None),
            "description": plugin.description,
            "organization_id": organization_id,
            "cloud_region_id": cloud_region_id,
            "monitor_object_id": monitor_object.id,
            "instance_type": monitor_object.name,
            "monitor_object_name": monitor_object.display_name or monitor_object.name,
            "metrics": metrics,
            "endpoint": endpoint,
            "line_protocol_example": line_without_timestamp,
            "line_protocol_example_without_timestamp": line_without_timestamp,
            "line_protocol_example_with_timestamp_ms": line_with_timestamp_ms,
        }
