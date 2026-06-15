from django.db import transaction
from django.db import IntegrityError

import nats_client
from apps.core.logger import node_logger as logger
from apps.node_mgmt.constants.database import DatabaseConstants, EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.management.services.node_init.collector_init import import_collector
from apps.node_mgmt.models import CloudRegion, SidecarEnv
from apps.node_mgmt.services.node import NodeService
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.tasks.installer import install_collector as install_collector_task
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.models import (
    CollectorConfiguration,
    ChildConfig,
    Collector,
    Node,
    NodeCollectorConfiguration,
    NodeOrganization,
)
from apps.node_mgmt.services.sidecar_cache import (
    invalidate_bulk_child_config_etags,
    invalidate_bulk_config_node_etags,
)
from apps.core.utils.crypto.aes_crypto import AESCryptor


class NatsService:
    @staticmethod
    def _allowed_architectures(node_arch: str) -> list[str]:
        normalized_arch = normalize_cpu_architecture(node_arch)
        if normalized_arch == NodeConstants.ARM64_ARCH:
            return [NodeConstants.ARM64_ARCH]
        if normalized_arch == NodeConstants.X86_64_ARCH:
            return [NodeConstants.X86_64_ARCH, ""]
        return ["", NodeConstants.X86_64_ARCH]

    @staticmethod
    def _resolve_collector_for_node(node: Node, collector_name: str):
        node_arch = normalize_cpu_architecture(getattr(node, "cpu_architecture", ""))
        allowed_architectures = NatsService._allowed_architectures(node_arch)
        collectors = list(
            Collector.objects.filter(
                name=collector_name,
                node_operating_system=node.operating_system,
                cpu_architecture__in=allowed_architectures,
            ).order_by("cpu_architecture", "id")
        )
        if not collectors:
            return None

        if node_arch == NodeConstants.ARM64_ARCH:
            return next((item for item in collectors if normalize_cpu_architecture(item.cpu_architecture) == NodeConstants.ARM64_ARCH), None)

        x86_match = next((item for item in collectors if normalize_cpu_architecture(item.cpu_architecture) == NodeConstants.X86_64_ARCH), None)
        legacy_x86_match = next((item for item in collectors if item.cpu_architecture == ""), None)
        return x86_match or legacy_x86_match

    def _ensure_parent_configs_for_child_configs(self, configs: list):
        if not configs:
            return

        required_pairs = {(config["node_id"], config["collector_name"]) for config in configs}
        node_ids = [node_id for node_id, _ in required_pairs]
        collector_names = [collector_name for _, collector_name in required_pairs]
        existing_pairs = set(
            CollectorConfiguration.objects.filter(nodes__id__in=node_ids, collector__name__in=collector_names)
            .values_list("nodes__id", "collector__name")
            .distinct()
        )
        missing_pairs = required_pairs - existing_pairs
        if not missing_pairs:
            return

        node_map = {node.id: node for node in Node.objects.filter(id__in=node_ids).select_related("cloud_region")}

        for node_id, collector_name in missing_pairs:
            node = node_map.get(node_id)
            if not node:
                raise BaseAppException(f"节点 {node_id} 不存在，无法为采集器 {collector_name} 创建父配置")

            collector = self._resolve_collector_for_node(node, collector_name)
            if not collector:
                raise BaseAppException(
                    "节点 %s 的采集器 %s 不存在（%s/%s）"
                    % (
                        node_id,
                        collector_name,
                        node.operating_system,
                        normalize_cpu_architecture(getattr(node, "cpu_architecture", "")) or NodeConstants.X86_64_ARCH,
                    )
                )

            if not collector.controller_default_run:
                raise BaseAppException(f"节点 {node_id} 的采集器 {collector_name} 未启用默认父配置创建(controller_default_run=False)")

            if not collector.default_config:
                raise BaseAppException(f"节点 {node_id} 的采集器 {collector_name} 缺少 default_config，无法创建父配置")

            NodeService._create_collector_default_config(node, collector)

            if not CollectorConfiguration.objects.filter(nodes__id=node_id, collector__name=collector_name).exists():
                raise BaseAppException(
                    f"节点 {node_id} 的采集器 {collector_name} 父配置自动创建失败，请检查 default_config、SIDECAR_INPUT_MODE 和云区域环境变量"
                )

    @staticmethod
    def _resolve_child_parent_config_id(base_configs: list[dict], node_id: str, collector_name: str, node_arch: str) -> str:
        exact_matches = []
        x86_matches = []
        legacy_x86_matches = []

        normalized_node_arch = normalize_cpu_architecture(node_arch)

        for item in base_configs:
            if item["nodes__id"] != node_id or item["collector__name"] != collector_name:
                continue

            collector_arch = normalize_cpu_architecture(item.get("collector__cpu_architecture"))
            if normalized_node_arch == NodeConstants.ARM64_ARCH:
                if collector_arch == NodeConstants.ARM64_ARCH:
                    exact_matches.append(item["id"])
                continue

            if collector_arch == NodeConstants.X86_64_ARCH:
                x86_matches.append(item["id"])
            elif item.get("collector__cpu_architecture", "") == "":
                legacy_x86_matches.append(item["id"])

        if len(exact_matches) > 1:
            raise BaseAppException(
                f"Ambiguous collector configuration for node {node_id} and collector {collector_name}: multiple exact architecture matches"
            )
        if exact_matches:
            return exact_matches[0]

        if normalized_node_arch != NodeConstants.ARM64_ARCH:
            if len(x86_matches) > 1:
                raise BaseAppException(
                    f"Ambiguous collector configuration for node {node_id} and collector {collector_name}: multiple x86_64 matches"
                )
            if x86_matches:
                return x86_matches[0]

            if len(legacy_x86_matches) > 1:
                raise BaseAppException(
                    f"Ambiguous collector configuration for node {node_id} and collector {collector_name}: multiple legacy x86-compatible matches"
                )
            if legacy_x86_matches:
                return legacy_x86_matches[0]

        raise BaseAppException(f"Collector configuration not found for node {node_id} and collector {collector_name}")

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
            "id",
            "cloud_region_id",
            "operating_system",
            "cpu_architecture",
        )
        cloud_region_map = {
            i["id"]: (
                i["cloud_region_id"],
                i["operating_system"],
                normalize_cpu_architecture(i.get("cpu_architecture")),
            )
            for i in cloud_regions
        }

        collectors = Collector.objects.filter(name__in=[i["collector_name"] for i in configs]).values(
            "name",
            "node_operating_system",
            "cpu_architecture",
            "id",
        )
        collector_map = {(i["name"], i["node_operating_system"], normalize_cpu_architecture(i.get("cpu_architecture"))): i["id"] for i in collectors}

        conf_objs, node_config_assos = [], []
        for config in configs:
            cloud_region_id, operating_system, cpu_architecture = cloud_region_map[config["node_id"]]
            normalized_arch = normalize_cpu_architecture(cpu_architecture)
            if normalized_arch == NodeConstants.ARM64_ARCH:
                candidate_keys = [(config["collector_name"], operating_system, NodeConstants.ARM64_ARCH)]
            elif normalized_arch == NodeConstants.X86_64_ARCH:
                candidate_keys = [
                    (config["collector_name"], operating_system, NodeConstants.X86_64_ARCH),
                    (config["collector_name"], operating_system, ""),
                ]
            else:
                candidate_keys = [
                    (config["collector_name"], operating_system, NodeConstants.X86_64_ARCH),
                    (config["collector_name"], operating_system, ""),
                ]

            collector_id = next((collector_map.get(key) for key in candidate_keys if collector_map.get(key)), None)
            if not collector_id:
                raise BaseAppException(
                    f"Collector {config['collector_name']} not found for {operating_system}/{cpu_architecture or NodeConstants.X86_64_ARCH}"
                )

            # 加密包含password的环境变量
            encrypted_env_config = self._encrypt_password_fields(config.get("env_config", {}))

            conf_objs.append(
                CollectorConfiguration(
                    id=config["id"],
                    name=config["name"],
                    config_template=config["content"],
                    collector_id=collector_id,
                    cloud_region_id=cloud_region_id,
                    env_config=encrypted_env_config,
                )
            )
            node_config_assos.append(NodeCollectorConfiguration(node_id=config["node_id"], collector_config_id=config["id"]))

        if conf_objs:
            CollectorConfiguration.objects.bulk_create(conf_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        if node_config_assos:
            NodeCollectorConfiguration.objects.bulk_create(
                node_config_assos,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
                ignore_conflicts=True,
            )

        invalidate_bulk_config_node_etags(configs)

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

        self._ensure_parent_configs_for_child_configs(configs)

        base_configs = list(
            CollectorConfiguration.objects.filter(
                nodes__id__in=[config["node_id"] for config in configs],
                collector__name__in=[config["collector_name"] for config in configs],
            )
            .values("id", "nodes__id", "collector__name", "collector__cpu_architecture")
            .distinct()
        )

        node_arch_map = {
            item["id"]: normalize_cpu_architecture(item.get("cpu_architecture"))
            for item in Node.objects.filter(id__in=[config["node_id"] for config in configs]).values("id", "cpu_architecture")
        }

        node_objs = []
        for config in configs:
            node_arch = node_arch_map.get(config["node_id"], "")
            collector_config_id = self._resolve_child_parent_config_id(
                base_configs=base_configs,
                node_id=config["node_id"],
                collector_name=config["collector_name"],
                node_arch=node_arch,
            )

            # 加密包含password的环境变量
            encrypted_env_config = self._encrypt_password_fields(config.get("env_config", {}))

            node_objs.append(
                ChildConfig(
                    id=config["id"],
                    collect_type=config["collect_type"],
                    config_type=config["type"],
                    content=config["content"],
                    collector_config_id=collector_config_id,
                    env_config=encrypted_env_config,
                    sort_order=config.get("sort_order", 0),
                    config_section=config.get("config_section", ""),
                )
            )

        if node_objs:
            try:
                ChildConfig.objects.bulk_create(node_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
            except IntegrityError as e:
                sample_ids = [config.id for config in node_objs[:3]]
                raise BaseAppException(
                    f"批量创建子配置失败，可能存在重复子配置ID或无效父配置关联: count={len(node_objs)}, sample_ids={sample_ids}, error={e}"
                ) from e
            except Exception as e:
                sample_ids = [config.id for config in node_objs[:3]]
                raise BaseAppException(f"批量创建子配置失败: count={len(node_objs)}, sample_ids={sample_ids}, error={e}") from e

        invalidate_bulk_child_config_etags([{"collector_config_id": config.collector_config_id} for config in node_objs])

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

        if content:
            child_config.content = content

        if env_config:
            # 智能合并并加密：只对变化的密码字段加密
            merged_env_config = self._merge_and_encrypt_env_config(child_config.env_config, env_config)
            child_config.env_config = merged_env_config

        child_config.save()

    def update_config_content(self, id, content, env_config=None):
        """更新配置内容"""

        if not content and not env_config:
            raise BaseAppException("Content or env_config must be provided for update.")

        config = CollectorConfiguration.objects.filter(id=id).first()
        if not config:
            raise BaseAppException("Configuration not found.")

        if content:
            config.config_template = content

        if env_config:
            # 智能合并并加密：只对变化的密码字段加密
            merged_env_config = self._merge_and_encrypt_env_config(config.env_config, env_config)
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
            "NATS_TLS_CA_WIN_FILE": "",
        }

    # 查询该云区域下的所有环境变量
    objs = SidecarEnv.objects.filter(
        key__in=["NATS_PROTOCOL", "NATS_TLS_CA_FILE", "NATS_TLS_CA_WIN_FILE"],
        cloud_region_id=node.cloud_region_id,
    )

    # 返回环境变量字典，默认值
    result = {
        "NATS_PROTOCOL": "nats",
        "NATS_TLS_CA_FILE": "",
        "NATS_TLS_CA_WIN_FILE": "",
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
def get_cloud_region_envconfig(cloud_region_id: str):
    """
    获取云区域的所有环境变量配置
    :param cloud_region_id: 云区域 ID
    :return: 环境变量字典
    """
    objs = SidecarEnv.objects.filter(cloud_region_id=cloud_region_id)
    variables = {}
    aes_obj = AESCryptor()

    for obj in objs:
        if obj.type == "secret":
            # 如果是密文，解密后使用
            try:
                value = aes_obj.decode(obj.value)
                variables[obj.key] = value
            except Exception as e:
                # 解密失败，记录警告日志并使用原值
                logger.warning(f"Failed to decrypt secret env variable {obj.key}: {e}")
                variables[obj.key] = obj.value
        else:
            # 如果是普通变量，直接使用
            variables[obj.key] = obj.value

    return variables


@nats_client.register
def get_cloud_region_proxy_address(cloud_region_id: str, organization_ids: list = None):
    """
    获取云区域代理地址
    优先从 CloudRegion.proxy_address 读取，若为空则回退到环境变量 PROXY_ADDRESS
    :param cloud_region_id: 云区域 ID
    :param organization_ids: 组织 ID 列表，非空时校验云区域归属
    :return: 代理地址
    """
    if organization_ids:
        has_access = NodeOrganization.objects.filter(
            node__cloud_region_id=cloud_region_id,
            organization__in=organization_ids,
        ).exists()
        if not has_access:
            return ""

    proxy_address = CloudRegion.objects.filter(id=cloud_region_id).values_list("proxy_address", flat=True).first() or ""
    if proxy_address:
        return proxy_address

    env_var = SidecarEnv.objects.filter(
        cloud_region_id=cloud_region_id,
        key=EnvVariableConstants.PROXY_ADDRESS_KEY,
    ).first()
    if not env_var:
        return ""

    if env_var.type == EnvVariableConstants.TYPE_SECRET and env_var.value:
        aes_obj = AESCryptor()
        try:
            return aes_obj.decode(env_var.value)
        except Exception as e:
            logger.warning(f"Failed to decrypt proxy env variable {env_var.key}: {e}")

    return env_var.value or ""


@nats_client.register
def node_list(query_data: dict):
    """获取节点列表"""
    organization_ids = query_data.get("organization_ids")
    cloud_region_id = query_data.get("cloud_region_id")
    name = query_data.get("name")
    ip = query_data.get("ip")
    os = query_data.get("os")
    page = query_data.get("page", 1)
    page_size = query_data.get("page_size", 10)
    is_active = query_data.get("is_active")
    is_manual = query_data.get("is_manual")
    is_container = query_data.get("is_container")
    permission_data = query_data.get("permission_data", {})
    skip_permission = query_data.get("skip_permission", False)
    return NodeService.get_node_list(
        organization_ids,
        cloud_region_id,
        name,
        ip,
        os,
        page,
        page_size,
        is_active,
        is_manual,
        is_container,
        permission_data,
        skip_permission,
    )


@nats_client.register
def get_node_names_by_ids(node_ids: list):
    """按节点ID批量获取节点名称。"""
    return NodeService.get_node_names_by_ids(node_ids)


@nats_client.register
def get_nodes_by_ids(node_ids: list):
    """按节点ID批量获取节点元数据。"""
    return NodeService.get_nodes_by_ids(node_ids)


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
def get_authorized_nodes_by_ids(node_ids: list, permission_data: dict = None):
    """根据节点ID列表获取当前调用方有权限的节点"""
    return NodeService.get_authorized_nodes_by_ids(node_ids, permission_data)


@nats_client.register
def update_child_config_content(data: dict):
    """更新实例子配置"""
    id = data.get("id")
    content = data.get("content")
    env_config = data.get("env_config")
    NatsService().update_child_config_content(id, content, env_config)


@nats_client.register
def update_config_content(data: dict):
    """更新配置内容"""
    id = data.get("id")
    content = data.get("content")
    env_config = data.get("env_config")
    NatsService().update_config_content(id, content, env_config)


@nats_client.register
def delete_child_configs(ids: list):
    """删除实例子配置"""
    NatsService().delete_child_configs(ids)


@nats_client.register
def delete_configs(ids: list):
    """删除实例子配置"""
    NatsService().delete_configs(ids)


def _install_collector_by_nats(data: dict):
    task_id = InstallerService.install_collector(data["collector_package"], data["nodes"])
    install_collector_task.delay(task_id)
    return {"task_id": task_id}


@nats_client.register
def install_collector(data: dict):
    """安装采集器"""
    return _install_collector_by_nats(data)


@nats_client.register
def install_managed_component(data: dict):
    """安装托管组件（当前复用采集器安装流程）"""
    return _install_collector_by_nats(data)
