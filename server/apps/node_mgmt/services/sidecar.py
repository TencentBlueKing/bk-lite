import hashlib
import json
from datetime import datetime, timezone
from string import Template
from django.core.cache import cache
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder

from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.database import DatabaseConstants
from apps.node_mgmt.utils.crypto_helper import EncryptedJsonResponse
from apps.node_mgmt.models.cloud_region import SidecarEnv
from apps.node_mgmt.models.sidecar import Node, Collector, CollectorConfiguration, NodeOrganization
from apps.node_mgmt.utils.sidecar import format_tags_dynamic
from apps.core.utils.crypto.aes_crypto import AESCryptor
from jinja2 import Template as JinjaTemplate

from apps.core.logger import node_logger as logger


class Sidecar:

    @staticmethod
    def generate_etag(data):
        """根据数据生成干净的 ETag，不加引号"""
        return hashlib.md5(data.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_response_etag(data, request):
        """
        根据响应数据和请求生成 ETag
        考虑加密情况，确保 ETag 基于实际发送内容
        """
        # 检查是否需要加密
        encryption_key = None
        if request:
            encryption_key = request.META.get('HTTP_X_ENCRYPTION_KEY')

        if encryption_key:
            # 如果需要加密，基于加密后的内容生成 ETag
            from apps.node_mgmt.utils.crypto_helper import encrypt_response_data
            try:
                encrypted_content = encrypt_response_data(data, encryption_key)
                return hashlib.md5(encrypted_content.encode('utf-8')).hexdigest()
            except Exception:
                # 加密失败，回退到明文内容，使用 Django JSON 编码器处理 datetime
                json_content = json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder)
                return hashlib.md5(json_content.encode('utf-8')).hexdigest()
        else:
            # 不需要加密，基于 JSON 内容生成 ETag，使用 Django JSON 编码器处理 datetime
            json_content = json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder)
            return hashlib.md5(json_content.encode('utf-8')).hexdigest()

    @staticmethod
    def get_version(request):
        """获取版本信息"""
        return EncryptedJsonResponse({"version": "5.0.0"}, request=request)

    @staticmethod
    def get_collectors(request):
        """获取采集器列表"""

        # 获取客户端的 ETag
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match:
            if_none_match = if_none_match.strip('"')

        # 从缓存中获取采集器的 ETag
        cached_etag = cache.get('collectors_etag')

        # 如果缓存的 ETag 存在且与客户端的相同，则返回 304 Not Modified
        if cached_etag and cached_etag == if_none_match:
            response = HttpResponse(status=304)
            response['ETag'] = cached_etag
            return response

        # 从数据库获取采集器列表
        collectors = list(Collector.objects.values())
        for collector in collectors:
            collector.pop("default_template")

        # 生成新的 ETag - 基于实际响应内容
        collectors_data = {'collectors': collectors}
        new_etag = Sidecar.generate_response_etag(collectors_data, request)

        # 更新缓存中的 ETag
        cache.set('collectors_etag', new_etag, ControllerConstants.E_CACHE_TIMEOUT)

        # 返回采集器列表和新的 ETag
        return EncryptedJsonResponse(collectors_data, headers={'ETag': new_etag}, request=request)

    @staticmethod
    def asso_groups(node_id: str, groups: list):
        if groups:
            NodeOrganization.objects.bulk_create(
                [NodeOrganization(node_id=node_id, organization=group) for group in groups],
                ignore_conflicts=True,
                batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
            )

    @staticmethod
    def update_groups(node_id: str, groups: list):
        """
        更新节点关联的组织
        :param node_id: 节点ID
        :param groups: 组织列表
        """
        # 删除现有的组织关联
        NodeOrganization.objects.filter(node_id=node_id).delete()

        # 重新关联新的组织
        Sidecar.asso_groups(node_id, groups)

    @staticmethod
    def update_node_client(request, node_id):
        """更新sidecar客户端信息"""

        # 获取客户端发送的ETag
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match:
            if_none_match = if_none_match.strip('"')

        # 从缓存中获取node的ETag
        cached_etag = cache.get(f"node_etag_{node_id}")

        # 如果缓存的ETag存在且与客户端的相同，则返回304 Not Modified
        if cached_etag and cached_etag == if_none_match:

            # 更新时间
            Node.objects.filter(id=node_id).update(updated_at=datetime.now(timezone.utc).isoformat())

            response = HttpResponse(status=304)
            response['ETag'] = cached_etag
            return response

        # 从请求体中获取数据
        request_data = dict(
            id=node_id,
            name=request.data.get("node_name", ""),
            **request.data.get("node_details", {}),
        )

        # 操作系统转小写
        request_data.update(operating_system=request_data['operating_system'].lower())

        logger.debug(f"node data: {request_data}")

        # 更新或创建 Sidecar 信息
        node = Node.objects.filter(id=node_id).first()

        # 处理标签数据
        tags_data = format_tags_dynamic(request_data.get("tags", []), ["group", "cloud"])

        if not node:

            # 补充云区域关联
            clouds = tags_data.get("cloud", [])
            if clouds:
                request_data.update(cloud_region_id=int(clouds[0]))

            # 创建节点
            node = Node.objects.create(**request_data)

            # 关联组织
            Sidecar.asso_groups(node_id, tags_data.get("group", []))

            # 创建默认的配置
            Sidecar.create_default_config(node)

        else:
            # 更新时间
            request_data.update(updated_at=datetime.now(timezone.utc).isoformat())

            # 更新节点
            Node.objects.filter(id=node_id).update(**request_data)

            # 更新组织关联(覆盖)
            Sidecar.update_groups(node_id, tags_data.get("group", []))

        # 预取相关数据，减少查询次数
        new_obj = Node.objects.prefetch_related('action_set', 'collectorconfiguration_set').get(id=node_id)

        # 构造响应数据
        response_data = dict(
            configuration={"update_interval": ControllerConstants.DEFAULT_UPDATE_INTERVAL, "send_status": True},  # 配置信息, DEFAULT_UPDATE_INTERVAL s更新一次
            configuration_override=True,  # 是否覆盖配置
            actions=[],  # 采集器状态
            assignments=[],  # 采集器配置
        )

        # 节点操作信息
        action_obj = new_obj.action_set.first()
        if action_obj:
            response_data.update(actions=action_obj.action)
            action_obj.delete()

        # 节点配置信息
        assignments = new_obj.collectorconfiguration_set.all()
        if assignments:
            response_data.update(
                assignments=[{"collector_id": i.collector_id, "configuration_id": i.id} for i in assignments])

        # 生成新的ETag - 基于实际响应内容
        new_etag = Sidecar.generate_response_etag(response_data, request)
        # 更新缓存中的ETag
        cache.set(f"node_etag_{node_id}", new_etag, ControllerConstants.E_CACHE_TIMEOUT)

        # 返回响应
        return EncryptedJsonResponse(status=202, data=response_data, headers={'ETag': new_etag}, request=request)

    @staticmethod
    def get_node_config(request, node_id, configuration_id):
        """获取节点配置信息"""

        # 获取客户端发送的 ETag
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match:
            if_none_match = if_none_match.strip('"')

        # 从缓存中获取配置的 ETag
        cached_etag = cache.get(f"configuration_etag_{configuration_id}")

        # 对比客户端的 ETag 和缓存的 ETag
        if cached_etag and cached_etag == if_none_match:
            response = HttpResponse(status=304)
            response['ETag'] = cached_etag
            return response

        # 从数据库获取节点信息
        node = Node.objects.filter(id=node_id).first()
        if not node:
            return EncryptedJsonResponse(status=404, data={"error": "Node not found"}, request=request)

        # 查询配置，并预取关联的子配置
        configuration = CollectorConfiguration.objects.filter(id=configuration_id).prefetch_related(
            'childconfig_set').first()
        if not configuration:
            return EncryptedJsonResponse(status=404, data={"error": "Configuration not found"}, request=request)

        # 合并子配置内容到模板
        merged_template = configuration.config_template
        for child_config in configuration.childconfig_set.all():
            # 假设子配置的 `content` 是纯文本格式，直接追加
            merged_template += f"\n# {child_config.collect_type} - {child_config.config_type}\n"
            merged_template += Sidecar.render_template(child_config.content, child_config.env_config)

        configuration_data = dict(
            id=configuration.id,
            collector_id=configuration.collector_id,
            name=configuration.name,
            template=merged_template,
            env_config=configuration.env_config or {},
        )
        # TODO test merged_template

        variables = Sidecar.get_variables(node)

        # 不在变量中渲染NATS_PASSWORD，走环境变量渲染
        variables.pop("NATS_PASSWORD", None)

        # 如果配置中有 env_config，则合并到变量中
        if configuration_data.get('env_config'):
            variables.update(configuration_data['env_config'])

        # 渲染配置模板
        configuration_data['template'] = Sidecar.render_template(configuration_data['template'], variables)

        # 生成新的 ETag - 基于实际响应内容
        new_etag = Sidecar.generate_response_etag(configuration_data, request)

        # 更新缓存中的 ETag
        cache.set(f"configuration_etag_{configuration_id}", new_etag, ControllerConstants.E_CACHE_TIMEOUT)

        # 返回配置信息和新的 ETag
        return EncryptedJsonResponse(configuration_data, headers={'ETag': new_etag}, request=request)

    @staticmethod
    def get_node_config_env(request, node_id, configuration_id):
        node = Node.objects.filter(id=node_id).first()
        if not node:
            return EncryptedJsonResponse(status=404, data={"error": "Node not found"}, request=request)

        # 查询配置，并预取关联的子配置
        obj = CollectorConfiguration.objects.filter(id=configuration_id).prefetch_related('childconfig_set').first()
        if not obj:
            return EncryptedJsonResponse(status=404, data={"error": "Configuration not found"}, request=request)

        # 获取云区域环境变量（仅获取 NATS_PASSWORD）
        nats_pwd_obj = SidecarEnv.objects.filter(key="NATS_PASSWORD", cloud_region=node.cloud_region_id).first()
        cloud_region_nats_password = {}
        if nats_pwd_obj:
            if nats_pwd_obj.type == "secret":
                # 如果是密文，解密后使用
                aes_obj = AESCryptor()
                cloud_region_nats_password = {nats_pwd_obj.key: aes_obj.decode(nats_pwd_obj.value)}
            else:
                # 如果是普通变量，直接使用
                cloud_region_nats_password = {nats_pwd_obj.key: nats_pwd_obj.value}

        # 合并环境变量：主配置的 env_config
        merged_env_config = {}
        if obj.env_config and isinstance(obj.env_config, dict):
            merged_env_config.update(obj.env_config)

        # 合并子配置的 env_config，按排序顺序处理
        for child_config in obj.childconfig_set.all():
            if child_config.env_config and isinstance(child_config.env_config, dict):
                merged_env_config.update(child_config.env_config)

        # 解密包含password的环境变量
        decrypted_env_config = {}
        aes_obj = AESCryptor()
        
        for key, value in merged_env_config.items():
            if 'password' in key.lower() and value:
                try:
                    # 对包含password的key进行解密
                    decrypted_env_config[key] = aes_obj.decode(str(value))
                except Exception as e:
                    logger.warning(f"Failed to decrypt password field {key}: {e}")
                    # 如果解密失败，可能是明文存储的，直接使用原值
                    decrypted_env_config[key] = str(value)
            else:
                decrypted_env_config[key] = str(value)

        # 合并云区域环境变量（仅 NATS_PASSWORD，优先级较低，配置级的env_config会覆盖同名变量）
        final_env_config = {}
        final_env_config.update(cloud_region_nats_password)
        final_env_config.update(decrypted_env_config)

        logger.debug(f"Merged env config for configuration {configuration_id}: {len(final_env_config)} variables (NATS_PASSWORD from cloud region: {'yes' if 'NATS_PASSWORD' in cloud_region_nats_password else 'no'})")

        return EncryptedJsonResponse(
            data=dict(
                id=configuration_id, 
                env_config=final_env_config
            ),
            request=request
        )

    @staticmethod
    def get_cloud_region_envconfig(node_obj):
        """获取云区域环境变量"""
        objs = SidecarEnv.objects.filter(cloud_region=node_obj.cloud_region_id)
        variables = {}
        for obj in objs:
            if obj.type == "secret":
                # 如果是密文，解密后使用
                aes_obj = AESCryptor()
                value = aes_obj.decode(obj.value)
                variables[obj.key] = value
            else:
                # 如果是普通变量，直接使用
                variables[obj.key] = obj.value
        return variables

    @staticmethod
    def get_variables(node_obj):
        """获取变量"""
        variables = Sidecar.get_cloud_region_envconfig(node_obj)
        node_dict = {
            "node__id": node_obj.id,
            "node__cloud_region": node_obj.cloud_region_id,
            "node__name": node_obj.name,
            "node__ip": node_obj.ip,
            "node__ip_filter": node_obj.ip.replace(".", "-").replace("*", "-").replace("*", ">"),
            "node__operating_system": node_obj.operating_system,
            "node__collector_configuration_directory": node_obj.collector_configuration_directory,
        }
        variables.update(node_dict)
        return variables

    @staticmethod
    def render_template(template_str, variables):
        """
        渲染字符串模板，将 ${变量} 替换为给定的值。

        :param template_str: 包含模板变量的字符串
        :param variables: 字典，包含变量名和对应值
        :return: 渲染后的字符串
        """
        template_str = template_str.replace('node.', 'node__')
        template = Template(template_str)
        return template.safe_substitute(variables)

    @staticmethod
    def create_default_config(node):

        collector_objs = Collector.objects.filter(enabled_default_config=True,
                                                  node_operating_system=node.operating_system)
        variables = Sidecar.get_cloud_region_envconfig(node)
        default_sidecar_mode = variables.get("SIDECAR_INPUT_MODE", "nats")

        for collector_obj in collector_objs:
            try:

                if not collector_obj.default_config:
                    continue

                config_template = collector_obj.default_config.get(default_sidecar_mode, None)

                if not config_template:
                    continue

                tpl = JinjaTemplate(config_template)
                _config_template = tpl.render(variables)

                # 如果已经存在关联的配置就跳过
                if CollectorConfiguration.objects.filter(collector=collector_obj, nodes=node).exists():
                    logger.info(
                        f"Node {node.id} already has a configuration for collector {collector_obj.name}, skipping.")
                    continue

                configuration = CollectorConfiguration.objects.create(
                    name=f'{collector_obj.name}-{node.id}',
                    collector=collector_obj,
                    config_template=_config_template,
                    is_pre=True,
                )
                configuration.nodes.add(node)

            except Exception as e:
                logger.error(f"create node {node.id} {collector_obj.name} default configuration failed {e}")
