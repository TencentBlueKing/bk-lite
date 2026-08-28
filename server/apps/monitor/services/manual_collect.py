from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.models.maintainer_info import maintainer_kwargs
from apps.core.utils.k8s_image_registry import build_kubectl_install_command
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.infra import InfraService
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class ManualCollectService:
    FLOW_ONLY_FIELDS = {"cloud_region_id", "ip", "fallback_sampling_rate", "enabled_protocols"}

    @staticmethod
    def _build_manual_collect_instance_data(data: dict):
        payload = dict(data)
        organizations = payload.pop("organizations", [])
        payload["auto"] = False
        payload["id"] = str(tuple([payload["id"]]))
        return payload, organizations

    @classmethod
    def _validate_create_fields(cls, data: dict, allow_flow_fields=False):
        if allow_flow_fields:
            return
        flow_only_fields = sorted(cls.FLOW_ONLY_FIELDS.intersection(data))
        if flow_only_fields:
            raise ValidationAppException(f"Use flow_asset for flow asset fields: {', '.join(flow_only_fields)}")

    @staticmethod
    def check_collect_status(object_id, instance_id) -> bool:
        """
        检查手动采集是否已经上报数据
        """

        # 实例ID格式转换
        _instance_id = parse_instance_id(instance_id)[0]

        monitor_object = MonitorObject.objects.filter(id=object_id).first()
        if not monitor_object:
            raise BaseAppException("监控对象不存在")
        query = monitor_object.default_metric
        if "}" not in query:
            raise BaseAppException("查询语句格式不正确")
        params_str = f'instance_id="{_instance_id}"'
        query = query.replace("}", f",{params_str}}}")
        resp = VictoriaMetricsAPI().query(query)
        result = resp.get("data", {}).get("result", [])
        if result:
            return True
        return False

    @staticmethod
    def asso_organization_to_instance(instance_id: str, organization_ids: list):
        """
        关联组织到手动采集实例
        """
        creates = [MonitorInstanceOrganization(monitor_instance_id=instance_id, organization=org_id) for org_id in organization_ids]
        MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)

    @staticmethod
    def create_organization_rule_by_child_object(monitor_object_id, instance_id, organization_ids):
        """
        为手动采集实例子对象创建分组规则
        """
        InstanceConfigService.create_default_rule(
            monitor_object_id,
            instance_id,
            organization_ids,
        )

    @staticmethod
    def create_manual_collect_instance(data: dict, *, allow_flow_fields=False, actor_context=None):
        """
        创建手动采集实例
        """
        ManualCollectService._validate_create_fields(data, allow_flow_fields=allow_flow_fields)
        data, organizations = ManualCollectService._build_manual_collect_instance_data(data)
        data.update(maintainer_kwargs(actor_context))
        MonitorObjectService.validate_new_instance_name_unique(data.get("monitor_object_id"), data.get("name"))
        # 建实例
        instance_obj = MonitorInstance.objects.create(**data)
        # 关联组织
        ManualCollectService.asso_organization_to_instance(instance_obj.id, organizations)
        # 创建子对象分组规则
        ManualCollectService.create_organization_rule_by_child_object(
            instance_obj.monitor_object_id,
            instance_obj.id,
            organizations,
        )
        return {"instance_id": instance_obj.id}

    @staticmethod
    def update_manual_collect_instance(instance_id: str, name=None, organizations=None, actor_context=None, **extra_fields):
        extra_fields.pop("enabled_protocols", None)
        MonitorObjectService.update_instance(
            instance_id=instance_id,
            name=name,
            organizations=organizations,
            actor_context=actor_context,
            **extra_fields,
        )
        return {"instance_id": instance_id}

    @staticmethod
    def generate_install_command(
        instance_id: str,
        cloud_region_id: str,
        image_registry_prefix: str | None = None,
    ) -> str:
        """
        生成 Kubernetes 安装命令

        :param cluster_name: 集群名称
        :param cloud_region_id: 云区域 ID
        :return: kubectl apply 命令字符串
        """

        cluster_name = parse_instance_id(instance_id)[0]

        # 通过 RPC 获取云区域环境变量
        from apps.rpc.node_mgmt import NodeMgmt

        node_mgmt_rpc = NodeMgmt()
        env_vars = node_mgmt_rpc.get_cloud_region_public_config(cloud_region_id)

        # 从云区域环境变量中获取服务器地址
        server_url = env_vars.get("NODE_SERVER_URL")
        if not server_url:
            raise BaseAppException(f"Missing NODE_SERVER_URL in cloud region {cloud_region_id}")

        # 调用 InfraService 生成限时令牌
        token = InfraService.generate_install_token(
            cluster_name,
            cloud_region_id,
            image_registry_prefix,
        )

        # 构造完整的 API URL（使用 open_api 前缀，统一开放 API 路由风格）
        api_url = f"{server_url.rstrip('/')}/api/v1/monitor/open_api/infra/render/"

        return build_kubectl_install_command(api_url, token)

    @staticmethod
    def get_install_config(data: dict) -> str:
        return ""
