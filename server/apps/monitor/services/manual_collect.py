import ast

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
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
    def generate_install_command(instance_id: str, cloud_region_id) -> str:
        """
        生成手动采集安装命令
        """
        # 实例ID格式转换
        try:
            _instance_id = ast.literal_eval(instance_id)[0]
        except Exception:
            _instance_id = instance_id
        install_command = (
            f"curl -sSO https://example.com/monitor-agent/install.sh && "
            f"bash install.sh --instance-id {_instance_id}"
        )
        return install_command

    @staticmethod
    def get_install_config(data: dict) -> str:
        return ""