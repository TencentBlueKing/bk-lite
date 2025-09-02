from django.core.cache import cache

import nats_client
from apps.node_mgmt.models import CloudRegion
from apps.node_mgmt.node_init.collector_init import import_collector
from apps.node_mgmt.services.node import NodeService
# from apps.core.logger import node_logger as logger

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.models import CollectorConfiguration, ChildConfig, Collector, Node, NodeCollectorConfiguration


class NatsService:
    def batch_create_configs(self, configs: list):
        """
        批量创建配置
        :param configs: 配置列表，每个配置包含以下字段：
            - id: 配置ID
            - name: 配置名称
            - content: 配置内容
            - node_id: 节点ID
            - collector_name: 采集器名称
            - env_config: 环境变量配置（可选）
        """

        cloud_regions = Node.objects.filter(id__in=[i["node_id"] for i in configs]).values(
            "id", "cloud_region_id", "operating_system")
        cloud_region_map = {i["id"]: (i["cloud_region_id"], i["operating_system"]) for i in cloud_regions}

        collectors = Collector.objects.filter(name__in=[i["collector_name"] for i in configs]).values(
            "name", "node_operating_system", "id"
        )
        collector_map = {(i["name"], i["node_operating_system"]): i["id"] for i in collectors}

        conf_objs, node_config_assos = [], []
        for config in configs:
            cloud_region_id, operating_system = cloud_region_map[config["node_id"]]
            collector_id = collector_map[(config["collector_name"], operating_system)]

            conf_objs.append(CollectorConfiguration(
                id=config["id"],
                name=config["name"],
                config_template=config["content"],
                collector_id=collector_id,
                cloud_region_id=cloud_region_id,
                env_config=config["env_config"],
            ))
            node_config_assos.append(
                NodeCollectorConfiguration(
                    node_id=config["node_id"],
                    collector_config_id=config["id"]
                )
            )
        if conf_objs:
            CollectorConfiguration.objects.bulk_create(conf_objs, batch_size=100)
        if node_config_assos:
            NodeCollectorConfiguration.objects.bulk_create(node_config_assos, batch_size=100, ignore_conflicts=True)

    def batch_create_child_configs(self, configs: list):
        """
        批量创建子配置
        :param configs: 配置列表，每个配置包含以下字段：
            - id: 子配置ID
            - collect_type: 采集类型
            - type: 配置类型
            - content: 配置内容
            - node_id: 节点ID
            - collector_name: 采集器名称
            - env_config: 环境变量配置（可选）
        """

        base_configs = CollectorConfiguration.objects.filter(
            nodes__id__in=[config["node_id"] for config in configs],
            collector__name__in=[config["collector_name"] for config in configs]
        ).values("id", "nodes__id", "collector__name").distinct()

        base_config_map = {(i["nodes__id"], i["collector__name"]): i["id"] for i in base_configs}

        node_objs = []
        for config in configs:
            node_objs.append(ChildConfig(
                id=config["id"],
                collect_type=config["collect_type"],
                config_type=config["type"],
                content=config["content"],
                collector_config_id=base_config_map[(config["node_id"], config["collector_name"])],
                env_config=config["env_config"],
            ))
        if node_objs:
            ChildConfig.objects.bulk_create(node_objs, batch_size=100)

    def get_child_configs_by_ids(self, ids: list):
        """根据子配置ID列表获取子配置对象"""
        child_configs = ChildConfig.objects.filter(id__in=ids)
        return [
            {
                "id": config.id,
                "collect_type": config.collect_type,
                "config_type": config.config_type,
                "content": config.content,
            }
            for config in child_configs
        ]

    def get_configs_by_ids(self, ids: list):
        """根据配置ID列表获取配置对象"""
        configs = CollectorConfiguration.objects.filter(id__in=ids)

        return [
            {
                "id": config.id,
                "name": config.name,
                "config_template": config.config_template,
                "env_config": config.env_config,
            }
            for config in configs
        ]

    def update_child_config_content(self, id, content, env_config=None):
        """更新子配置内容"""


        if not content and not env_config:
            raise BaseAppException("Content or env_config must be provided for update.")

        child_config = ChildConfig.objects.filter(id=id).first()

        cache.delete(f"configuration_etag_{child_config.collector_config_id}")

        if env_config:
            child_config.env_config = env_config

        if content:
            child_config.content = content

        child_config.save()

    def update_config_content(self, id, content, env_config=None):
        """更新配置内容"""

        if not content and not env_config:
            raise BaseAppException("Content or env_config must be provided for update.")

        config = CollectorConfiguration.objects.filter(id=id).first()
        cache.delete(f"configuration_etag_{config.id}")

        if config:
            config.config_template = content

        if env_config:
            config.env_config = env_config

        config.save()

    def delete_child_configs(self, ids):
        """删除子配置"""
        ChildConfig.objects.filter(id__in=ids).delete()

    def delete_configs(self, ids):
        """删除配置"""
        CollectorConfiguration.objects.filter(id__in=ids).delete()


@nats_client.register
def cloud_region_list():
    """获取云区域列表"""
    objs = CloudRegion.objects.all()
    return [{"id": obj.id, "name": obj.name} for obj in objs]


@nats_client.register
def node_list(query_data: dict):
    """获取节点列表"""
    organization_ids = query_data.get('organization_ids')
    cloud_region_id = query_data.get('cloud_region_id')
    name = query_data.get('name')
    ip = query_data.get('ip')
    os = query_data.get('os')
    page = query_data.get('page', 1)
    page_size = query_data.get('page_size', 10)
    is_active = query_data.get('is_active')
    return NodeService.get_node_list(organization_ids, cloud_region_id, name, ip, os, page, page_size, is_active)


@nats_client.register
def collector_list(query_data: dict):
    return []


@nats_client.register
def import_collectors(collectors: list):
    """导入采集器"""
    # logger.info(f"import_collectors: {collectors}")
    return import_collector(collectors)


@nats_client.register
def batch_add_node_child_config(configs: list):
    """批量添加子配置"""
    # logger.info(f"batch_add_node_child_config: {configs}")
    NatsService().batch_create_child_configs(configs)


@nats_client.register
def batch_add_node_config(configs: list):
    """批量添加配置"""
    # logger.info(f"batch_add_node_config: {configs}")
    NatsService().batch_create_configs(configs)


@nats_client.register
def get_child_configs_by_ids(ids: list):
    """根据ID获取子配置"""
    return NatsService().get_child_configs_by_ids(ids)


@nats_client.register
def get_configs_by_ids(ids: list):
    """根据ID获取配置"""
    return NatsService().get_configs_by_ids(ids)


@nats_client.register
def update_child_config_content(data: dict):
    """更新实例子配置"""
    id = data.get('id')
    content = data.get('content')
    env_config = data.get('env_config')
    NatsService().update_child_config_content(id, content, env_config)


@nats_client.register
def update_config_content(data: dict):
    """更新配置内容"""
    id = data.get('id')
    content = data.get('content')
    env_config = data.get('env_config')
    NatsService().update_config_content(id, content, env_config)


@nats_client.register
def delete_child_configs(ids: list):
    """删除实例子配置"""
    NatsService().delete_child_configs(ids)


@nats_client.register
def delete_configs(ids: list):
    """删除实例子配置"""
    NatsService().delete_configs(ids)