from django.core.cache import cache
from django.db import transaction

import nats_client
from apps.node_mgmt.constants.database import DatabaseConstants, EnvVariableConstants
from apps.node_mgmt.management.services.node_init.collector_init import import_collector
from apps.node_mgmt.models import CloudRegion, SidecarEnv
from apps.node_mgmt.services.node import NodeService

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.models import CollectorConfiguration, ChildConfig, Collector, Node, NodeCollectorConfiguration
from apps.core.utils.crypto.aes_crypto import AESCryptor


class NatsService:
    @staticmethod
    def _encrypt_password_fields(env_config: dict) -> dict:
        """加密包含password的环境变量字段"""
        if not env_config or not isinstance(env_config, dict):
            return env_config
        
        encrypted_config = {}
        aes_obj = AESCryptor()
        
        for key, value in env_config.items():
            if EnvVariableConstants.SENSITIVE_FIELD_KEYWORD in key.lower() and value:
                # 对包含password的key进行加密
                encrypted_config[key] = aes_obj.encode(str(value))
            else:
                encrypted_config[key] = value
        
        return encrypted_config

    @staticmethod
    def _merge_and_encrypt_env_config(old_env_config: dict, new_env_config: dict) -> dict:
        """
        合并并智能加密环境变量配置
        只对变化的密码字段进行加密，未变化的保持原值

        :param old_env_config: 数据库中的原配置（已加密）
        :param new_env_config: 前端传来的新配置（可能包含明文或未修改的加密值）
        :return: 合并后的配置（密码字段已加密）
        """
        if not new_env_config or not isinstance(new_env_config, dict):
            return new_env_config or {}

        old_env_config = old_env_config or {}
        merged_config = {}
        aes_obj = AESCryptor()

        for key, value in new_env_config.items():
            # 如果不是密码字段，直接使用新值
            if EnvVariableConstants.SENSITIVE_FIELD_KEYWORD not in key.lower() or not value:
                merged_config[key] = value
                continue

            # 对于密码字段：
            old_value = old_env_config.get(key)

            # 如果值未变化（前端未编辑），保持原加密值
            if old_value and value == old_value:
                merged_config[key] = old_value
            else:
                # 值发生变化，说明是新的明文密码，需要加密
                merged_config[key] = aes_obj.encode(str(value))

        return merged_config

    @transaction.atomic
    def batch_create_configs_and_child_configs(self, configs: list, child_configs: list):
        """
        批量创建配置及其子配置（带事务保护）
        :param configs: 配置列表
        :param child_configs: 子配置列表
        """
        self._batch_create_configs_internal(configs)
        self._batch_create_child_configs_internal(child_configs)

    def _batch_create_configs_internal(self, configs: list):
        """
        批量创建配置（内部方法，不带事务装饰器，由调用方控制事务）
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

            # 加密包含password的环境变量
            encrypted_env_config = self._encrypt_password_fields(config.get("env_config", {}))

            conf_objs.append(CollectorConfiguration(
                id=config["id"],
                name=config["name"],
                config_template=config["content"],
                collector_id=collector_id,
                cloud_region_id=cloud_region_id,
                env_config=encrypted_env_config,
            ))
            node_config_assos.append(
                NodeCollectorConfiguration(
                    node_id=config["node_id"],
                    collector_config_id=config["id"]
                )
            )

        if conf_objs:
            CollectorConfiguration.objects.bulk_create(conf_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        if node_config_assos:
            NodeCollectorConfiguration.objects.bulk_create(node_config_assos, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE, ignore_conflicts=True)

    @transaction.atomic
    def batch_create_configs(self, configs: list):
        """
        批量创建配置（公共接口，带事务保护）
        :param configs: 配置列表
        """
        self._batch_create_configs_internal(configs)

    def _batch_create_child_configs_internal(self, configs: list):
        """
        批量创建子配置（内部方法，不带事务装饰器，由调用方控制事务）
        :param configs: 配置列表，每个配置包含以下字段：
            - id: 子配置ID
            - collect_type: 采集类型
            - type: 配置类型
            - content: 配置内容
            - node_id: 节点ID
            - collector_name: 采集器名称
            - env_config: 环境变量配置（可选）
            - sort_order: 排序（可选）
        """

        base_configs = CollectorConfiguration.objects.filter(
            nodes__id__in=[config["node_id"] for config in configs],
            collector__name__in=[config["collector_name"] for config in configs]
        ).values("id", "nodes__id", "collector__name").distinct()

        base_config_map = {(i["nodes__id"], i["collector__name"]): i["id"] for i in base_configs}

        node_objs = []
        for config in configs:
            # 加密包含password的环境变量
            encrypted_env_config = self._encrypt_password_fields(config.get("env_config", {}))

            node_objs.append(ChildConfig(
                id=config["id"],
                collect_type=config["collect_type"],
                config_type=config["type"],
                content=config["content"],
                collector_config_id=base_config_map[(config["node_id"], config["collector_name"])],
                env_config=encrypted_env_config,
                sort_order=config.get("sort_order", 0),
            ))

        if node_objs:
            ChildConfig.objects.bulk_create(node_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

    @transaction.atomic
    def batch_create_child_configs(self, configs: list):
        """
        批量创建子配置（公共接口，带事务保护）
        :param configs: 配置列表
        """
        self._batch_create_child_configs_internal(configs)

    def get_child_configs_by_ids(self, ids: list):
        """根据子配置ID列表获取子配置对象"""
        child_configs = ChildConfig.objects.filter(id__in=ids)
        return [
            {
                "id": config.id,
                "collect_type": config.collect_type,
                "config_type": config.config_type,
                "content": config.content,
                "env_config": config.env_config,
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
        if not child_config:
            raise BaseAppException("Child config not found.")

        cache.delete(f"configuration_etag_{child_config.collector_config_id}")

        if content:
            child_config.content = content

        if env_config:
            # 智能合并并加密：只对变化的密码字段加密
            merged_env_config = self._merge_and_encrypt_env_config(
                child_config.env_config,
                env_config
            )
            child_config.env_config = merged_env_config

        child_config.save()

    def update_config_content(self, id, content, env_config=None):
        """更新配置内容"""

        if not content and not env_config:
            raise BaseAppException("Content or env_config must be provided for update.")

        config = CollectorConfiguration.objects.filter(id=id).first()
        if not config:
            raise BaseAppException("Configuration not found.")
            
        cache.delete(f"configuration_etag_{config.id}")

        if content:
            config.config_template = content

        if env_config:
            # 智能合并并加密：只对变化的密码字段加密
            merged_env_config = self._merge_and_encrypt_env_config(
                config.env_config,
                env_config
            )
            config.env_config = merged_env_config

        config.save()

    def delete_child_configs(self, ids):
        """删除子配置"""
        ChildConfig.objects.filter(id__in=ids).delete()

    def delete_configs(self, ids):
        """删除配置"""
        CollectorConfiguration.objects.filter(id__in=ids).delete()


@nats_client.register
def cloudregion_tls_env_by_node_id(node_id):
    """根据节点ID获取对应的边车环境变量配置"""
    # 先查询节点获取云区域ID
    node = Node.objects.filter(id=node_id).first()
    if not node:
        return {
            "NATS_PROTOCOL": "nats",
            "NATS_TLS_CA_FILE": "",
        }

    # 查询该云区域下的所有环境变量
    objs = SidecarEnv.objects.filter(key__in=["NATS_PROTOCOL", "NATS_TLS_CA_FILE"], cloud_region_id=node.cloud_region_id)

    # 返回环境变量字典，默认值
    result = {
        "NATS_PROTOCOL": "nats",
        "NATS_TLS_CA_FILE": "",
    }
    
    # 用查询到的值覆盖默认值
    for obj in objs:
        result[obj.key] = obj.value

    return result


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
    permission_data = query_data.get('permission_data', {})
    return NodeService.get_node_list(organization_ids, cloud_region_id, name, ip, os, page, page_size, is_active, permission_data)


@nats_client.register
def collector_list(query_data: dict):
    return []


@nats_client.register
def import_collectors(collectors: list):
    """导入采集器"""
    # logger.info(f"import_collectors: {collectors}")
    return import_collector(collectors)


@nats_client.register
def batch_create_configs_and_child_configs(configs: list, child_configs: list):
    """批量创建配置和子配置（原子性操作）"""
    NatsService().batch_create_configs_and_child_configs(configs, child_configs)


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
