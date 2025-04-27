import logging

import nats_client

from apps.node_mgmt.child_config.common import ChildConfigCommon
from apps.node_mgmt.services.node import NodeService

logger = logging.getLogger("app")


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
    return NodeService.get_node_list(organization_ids, cloud_region_id, name, ip, os, page, page_size)


@nats_client.register
def collector_list(query_data: dict):
    return []


@nats_client.register
def batch_setting_node_child_config(data: dict):
    """批量对节点设置子配置"""
    logger.info(f"batch_setting_node_child_config: {data}")
    object_type = data.get('object_type')
    nodes = data.get('nodes')
    ChildConfigCommon(object_type).batch_setting_node_config(nodes)


@nats_client.register
def get_instance_child_config(query_data: dict):
    """获取实例子配置"""
    collect_type = query_data.get('collect_type')
    config_type = query_data.get('config_type')
    collect_instance_id = query_data.get('collect_instance_id')
    return ChildConfigCommon.get_child_config_by_instance_id(collect_type, config_type, collect_instance_id)


@nats_client.register
def update_instance_child_config(data: dict):
    """更新实例子配置"""
    id = data.get('id')
    content = data.get('content')
    ChildConfigCommon.update_instance_child_config(id, content)


@nats_client.register
def delete_instance_child_config(instance_ids: list):
    """更新实例子配置"""
    ChildConfigCommon.delete_child_config_by_instance_id(instance_ids)