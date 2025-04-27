from apps.node_mgmt.child_config.telegraf.database import DataBaseConfig
from apps.node_mgmt.child_config.telegraf.docker import DockerConfig
from apps.node_mgmt.child_config.telegraf.host import HostConfig
from apps.node_mgmt.child_config.telegraf.http import HttpConfig
from apps.node_mgmt.child_config.telegraf.ipmi import IpmiConfig
from apps.node_mgmt.child_config.telegraf.middleware import MiddlewareConfig
from apps.node_mgmt.child_config.telegraf.ping import PingConfig
from apps.node_mgmt.child_config.telegraf.snmp import SnmpConfig
from apps.node_mgmt.child_config.telegraf.trap import TrapConfig
from apps.node_mgmt.child_config.telegraf.web import WebConfig
from apps.node_mgmt.models.sidecar import ChildConfig

OBJECT_TYPE_MAP = {
    "host": HostConfig.patch_set_node_config,
    "web": WebConfig.patch_set_node_config,
    "ping": PingConfig.patch_set_node_config,
    "ipmi": IpmiConfig.patch_set_node_config,
    "trap": TrapConfig.patch_set_node_config,
    "snmp": SnmpConfig.patch_set_node_config,
    "middleware": MiddlewareConfig.patch_set_node_config,
    "docker": DockerConfig.patch_set_node_config,
    "database": DataBaseConfig.patch_set_node_config,
    "http": HttpConfig.patch_set_node_config,
}


class ChildConfigCommon:
    def __init__(self, object_type):
        self.object_type = object_type

    def batch_setting_node_config(self, nodes):
        """批量设置节点配置"""
        method = OBJECT_TYPE_MAP.get(self.object_type)
        if not method:
            raise ValueError(f"Unsupported object type: {self.object_type}")
        method(nodes)

    @staticmethod
    def get_child_config_by_instance_id(collect_type, config_type, collect_instance_id):
        """根据实例ID获取配置"""
        qs = ChildConfig.objects.filter()
        if collect_type:
            qs = qs.filter(collect_type=collect_type)
        if config_type:
            qs = qs.filter(config_type=config_type)
        if collect_instance_id:
            qs = qs.filter(collect_instance_id=collect_instance_id)

        qs = qs.select_related('collector_config').prefetch_related('collector_config__nodes')
        result = [
            {
                "id": obj.id,
                "collect_type": obj.collect_type,
                "config_type": obj.config_type,
                "collect_instance_id": obj.collect_instance_id,
                "content": obj.content,
                "collector_config_id": obj.collector_config_id,
                "agents": [f"{node.ip}-{node.cloud_region_id}" for node in obj.collector_config.nodes.all()],
            }
            for obj in qs
        ]
        return result

    @staticmethod
    def update_instance_child_config(id, content):
        """更新实例子配置"""
        ChildConfig.objects.filter(id=id).update(content=content)

    @staticmethod
    def delete_child_config_by_instance_id(instance_ids):
        """删除实例子配置"""
        ChildConfig.objects.filter(collect_instance_id__in=instance_ids).delete()