from urllib.parse import urlsplit

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.monitor.models import MonitorObject
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.rpc.node_mgmt import NodeMgmt


class FlowAccessGuideService:
    PROTOCOL_PORT_MAP = {"netflow": 2056, "sflow": 6343}

    @classmethod
    def get_listener_endpoint(cls, protocol, cloud_region_id):
        FlowOnboardingService._validate_protocol(protocol)
        env_config = NodeMgmt().get_cloud_region_envconfig(cloud_region_id)
        if not isinstance(env_config, dict):
            raise BaseAppException("获取云区域环境变量失败")

        node_server_url = env_config.get("NODE_SERVER_URL")
        if not node_server_url:
            raise BaseAppException("当前云区域未配置 NODE_SERVER_URL，无法拼接 Flow 接入地址")

        parts = urlsplit(node_server_url)
        host = parts.hostname
        if not parts.scheme or not host:
            raise BaseAppException("NODE_SERVER_URL 配置不合法，无法拼接 Flow 接入地址")
        if ":" in host:
            host = f"[{host}]"
        return f"udp://{host}:{cls.PROTOCOL_PORT_MAP[protocol]}"

    @classmethod
    def build_document(cls, *, protocol, cloud_region_id, monitor_object=None, monitor_object_id=None):
        FlowOnboardingService._validate_protocol(protocol)
        monitor_object = cls._resolve_monitor_object(monitor_object=monitor_object, monitor_object_id=monitor_object_id)
        endpoint = cls.get_listener_endpoint(protocol, cloud_region_id)
        protocol_name = "NetFlow" if protocol == "netflow" else "sFlow"

        return {
            "protocol": protocol,
            "protocol_name": protocol_name,
            "endpoint": endpoint,
            "cloud_region_id": cloud_region_id,
            "monitor_object_id": monitor_object.id,
            "monitor_object_name": monitor_object.display_name or monitor_object.name,
            "instructions": [
                f"在设备上开启 {protocol_name} 导出，并将目标地址指向当前接入地址。",
                "保持设备源地址与已绑定的 Flow 资产 IP 一致。",
                "完成配置后使用检测接口确认最近时间窗内已收到对应协议数据。",
            ],
            "sampling_rule": (
                "系统统一消费 effective_sampling_rate。接收侧按 "
                "SAMPLING_INTERVAL、SAMPLING_ALGORITHM、sampling_rate、samplingRate 的顺序归一化；"
                "若仍缺失则回退到资产 fallback_sampling_rate。"
            ),
            "detect_hint": "检测成功的标准是最近时间窗内收到该资产对应协议的实际 Flow 数据。",
        }

    @staticmethod
    def _resolve_monitor_object(*, monitor_object=None, monitor_object_id=None):
        if monitor_object is None:
            if monitor_object_id in (None, ""):
                raise ValidationAppException("Monitor object does not exist")
            monitor_object = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_object:
            raise ValidationAppException("Monitor object does not exist")
        if monitor_object.name not in FlowOnboardingService.SUPPORTED_MONITOR_OBJECT_NAMES:
            raise ValidationAppException("Unsupported flow monitor object")
        return monitor_object
