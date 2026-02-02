import ast

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.infra import InfraService
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class ManualCollectService:

    @staticmethod
    def check_collect_status(object_id, instance_id) -> bool:
        """
        检查手动采集是否已经上报数据
        """

        # 实例ID格式转换
        try:
            _instance_id = ast.literal_eval(instance_id)[0]
        except Exception:
            _instance_id = instance_id

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
        creates = [
            MonitorInstanceOrganization(
                monitor_instance_id=instance_id,
                organization=org_id
            ) for org_id in organization_ids
        ]
        MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)

    @staticmethod
    def create_organization_rule_by_child_object(monitor_object_id, instance_id, organization_ids):
        """
        为手动采集实例子对象创建分组规则
        """
        rule_ids = InstanceConfigService.create_default_rule(
            monitor_object_id,
            instance_id,
            organization_ids,
        )


    @staticmethod
    def create_manual_collect_instance(data: dict):
        """
        创建手动采集实例
        """
        organizations = data.pop("organizations", [])
        instance_id = str(tuple([data["id"]]))
        data.update(id=instance_id)
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
    def generate_install_command(instance_id: str, cloud_region_id: str) -> str:
        """
        生成 Kubernetes 安装命令

        :param cluster_name: 集群名称
        :param cloud_region_id: 云区域 ID
        :return: kubectl apply 命令字符串
        """

        try:
            cluster_name = ast.literal_eval(instance_id)[0]
        except Exception:
            cluster_name = instance_id

        # 通过 RPC 获取云区域环境变量
        from apps.rpc.node_mgmt import NodeMgmt

        node_mgmt_rpc = NodeMgmt()
        env_vars = node_mgmt_rpc.get_cloud_region_envconfig(cloud_region_id)

        # 从云区域环境变量中获取服务器地址
        server_url = env_vars.get('NODE_SERVER_URL')
        if not server_url:
            raise BaseAppException(f"Missing NODE_SERVER_URL in cloud region {cloud_region_id}")

        # 调用 InfraService 生成限时令牌
        token = InfraService.generate_install_token(cluster_name, cloud_region_id)

        # 构造完整的 API URL（使用 open_api 前缀，统一开放 API 路由风格）
        api_url = f"{server_url.rstrip('/')}/api/v1/monitor/open_api/infra/render/"

        # 构造 curl 命令，使用令牌而不是直接传递参数
        # 添加 -k 参数跳过 SSL 证书验证（针对自签名证书或内网环境）
        install_command = (
            f"curl -sSLk -X POST "
            f"-H 'Content-Type: application/json' "
            f"{api_url} "
            f"-d '{{\"token\":\"{token}\"}}' "
            f"| kubectl apply -f -"
        )
        return install_command

    @staticmethod
    def get_install_config(data: dict) -> str:
        return ""
