from urllib.parse import urlsplit

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.monitor.models import MonitorObject
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.rpc.node_mgmt import NodeMgmt


class FlowAccessGuideService:
    PROTOCOL_PORT_MAP = {"netflow": 2056, "sflow": 6343}
    LISTENER_ENDPOINT_SPECS = {
        "netflow": [
            ("netflow_v5", "NetFlow v5", 2055),
            ("netflow_v9", "NetFlow v9", 2056),
        ],
        "sflow": [
            ("sflow", "sFlow", 6343),
        ],
    }

    @classmethod
    def get_listener_endpoint(cls, protocol, cloud_region_id):
        FlowOnboardingService._validate_protocol(protocol)
        host = cls._get_listener_host(cloud_region_id)
        return cls._build_udp_endpoint(host, cls.PROTOCOL_PORT_MAP[protocol])

    @classmethod
    def _get_listener_host(cls, cloud_region_id):
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
        return host

    @classmethod
    def _build_udp_endpoint(cls, host, port):
        return f"udp://{host}:{port}"

    @classmethod
    def get_listener_endpoints(cls, protocol, cloud_region_id):
        FlowOnboardingService._validate_protocol(protocol)
        host = cls._get_listener_host(cloud_region_id)
        return [
            {
                "protocol": item_protocol,
                "protocol_name": protocol_name,
                "endpoint": cls._build_udp_endpoint(host, port),
                "port": port,
            }
            for item_protocol, protocol_name, port in cls.LISTENER_ENDPOINT_SPECS[protocol]
        ]

    @classmethod
    def build_document(cls, *, protocol, cloud_region_id, monitor_object=None, monitor_object_id=None):
        FlowOnboardingService._validate_protocol(protocol)
        monitor_object = cls._resolve_monitor_object(monitor_object=monitor_object, monitor_object_id=monitor_object_id)
        endpoint = cls.get_listener_endpoint(protocol, cloud_region_id)
        listener_endpoints = cls.get_listener_endpoints(protocol, cloud_region_id)
        protocol_name = "NetFlow" if protocol == "netflow" else "sFlow"
        endpoint_tip = (
            "NetFlow v5 使用 UDP 2055，NetFlow v9 使用 UDP 2056，请按设备导出版本选择对应端口。"
            if protocol == "netflow"
            else "sFlow 使用 UDP 6343。"
        )

        return {
            "protocol": protocol,
            "protocol_name": protocol_name,
            "endpoint": endpoint,
            "listener_endpoints": listener_endpoints,
            "cloud_region_id": cloud_region_id,
            "monitor_object_id": monitor_object.id,
            "monitor_object_name": monitor_object.display_name or monitor_object.name,
            "instructions": [
                f"在设备上开启 {protocol_name} 导出，并将目标地址指向当前接入地址。",
                endpoint_tip,
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
