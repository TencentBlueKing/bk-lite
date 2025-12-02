from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class ManualCollectService:

    @staticmethod
    def check_collect_status(query: str) -> bool:
        """
        检查手动采集是否已经上报数据
        """
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
                organization_id=org_id
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