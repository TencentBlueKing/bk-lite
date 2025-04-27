import hashlib
import logging
from string import Template

from django.core.cache import cache
from django.http import JsonResponse
from django.utils.http import quote_etag

from apps.node_mgmt.constants import L_INSTALL_DOWNLOAD_URL, L_SIDECAR_DOWNLOAD_URL, W_SIDECAR_DOWNLOAD_URL, LOCAL_HOST
from apps.node_mgmt.default_config.nats_executor import create_nats_executor_config
from apps.node_mgmt.default_config.telegraf import create_telegraf_config
from apps.node_mgmt.models.cloud_region import SidecarEnv
from apps.node_mgmt.models.sidecar import Node, Collector, CollectorConfiguration


logger = logging.getLogger("app")


class Sidecar:

    @staticmethod
    def generate_etag(data):
        """根据Collector列表生成ETag"""
        return quote_etag(hashlib.md5(data.encode('utf-8')).hexdigest())

    @staticmethod
    def get_version():
        """获取版本信息"""
        return JsonResponse({"version": "5.0.0"})

    @staticmethod
    def get_collectors(request):
        """获取采集器列表"""

        # 获取客户端的 ETag
        if_none_match = request.headers.get('If-None-Match')

        # 从缓存中获取采集器的 ETag
        cached_etag = cache.get('collectors_etag')

        # 如果缓存的 ETag 存在且与客户端的相同，则返回 304 Not Modified
        if cached_etag and cached_etag == if_none_match:
            return JsonResponse(status=304, data={}, headers={'ETag': cached_etag})

        # 从数据库获取采集器列表
        collectors = list(Collector.objects.values())
        for collector in collectors:
            collector.pop("default_template")

        # 生成新的 ETag
        _collectors = JsonResponse(collectors, safe=False).content
        new_etag = Sidecar.generate_etag(_collectors.decode('utf-8'))

        # 更新缓存中的 ETag
        cache.set('collectors_etag', new_etag)

        # 返回采集器列表和新的 ETag
        return JsonResponse({'collectors': collectors}, headers={'ETag': new_etag})

    @staticmethod
    def update_node_client(request, node_id):
        """更新sidecar客户端信息"""

        # 获取客户端发送的ETag
        if_none_match = request.headers.get('If-None-Match')

        # 从缓存中获取node的ETag
        cached_etag = cache.get(f"node_etag_{node_id}")

        # 如果缓存的ETag存��且与客户端的相同，则返回304 Not Modified
        if cached_etag and cached_etag == if_none_match:
            return JsonResponse(status=304, data={}, headers={'ETag': cached_etag})

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

        if not node:
            # 创建节点
            node = Node.objects.create(**request_data)

            # 创建默认的 Telegraf 配置
            create_telegraf_config(node)

            # 创建默认的 NATS Executor 配置
            create_nats_executor_config(node)

        else:
            # 更新节点
            Node.objects.filter(id=node_id).update(**request_data)

        # 预取相关数据，减少查询次数
        new_obj = Node.objects.prefetch_related('action_set', 'collectorconfiguration_set').get(id=node_id)

        # 构造响应数据
        response_data = dict(
            configuration={"update_interval": 5, "send_status": True},  # 配置信息, 5s更新一次
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

        # 生成新的ETag
        _response_data = JsonResponse(response_data).content
        new_etag = Sidecar.generate_etag(_response_data.decode('utf-8'))
        # 更新缓存中的ETag
        cache.set(f"node_etag_{node_id}", new_etag)

        # 返回响应
        return JsonResponse(status=202, data=response_data, headers={'ETag': new_etag})

    @staticmethod
    def get_node_config(request, node_id, configuration_id):
        """获取节点配置信息"""

        # 获取客户端发送的 ETag
        if_none_match = request.headers.get('If-None-Match')

        # 从缓存中获取配置的 ETag
        cached_etag = cache.get(f"configuration_etag_{configuration_id}")

        # 对比客户端的 ETag 和缓存的 ETag
        if cached_etag and cached_etag == if_none_match:
            return JsonResponse(status=304, data={}, headers={'ETag': cached_etag})

        # 从数据库获取节点信息
        node = Node.objects.filter(id=node_id).first()
        if not node:
            return JsonResponse(status=404, data={}, manage="Node collector Configuration not found")

        # 查询配置，并预取关联的子配置
        configuration = CollectorConfiguration.objects.filter(id=configuration_id).prefetch_related(
            'childconfig_set').first()
        if not configuration:
            return JsonResponse(status=404, data={}, manage="Configuration not found")

        # 合并子配置内容到模板
        merged_template = configuration.config_template
        for child_config in configuration.childconfig_set.all():
            # 假设子配置的 `content` 是纯文本格式，直接追加
            merged_template += f"\n# {child_config.collect_type} - {child_config.config_type}\n"
            merged_template += child_config.content

        configuration = dict(
            id=configuration.id,
            collector_id=configuration.collector_id,
            name=configuration.name,
            template=merged_template,
        )
        # TODO test merged_template

        # 生成新的 ETag
        _configuration = JsonResponse(configuration).content
        new_etag = Sidecar.generate_etag(_configuration.decode('utf-8'))

        # 更新缓存中的 ETag
        cache.set(f"configuration_etag_{configuration_id}", new_etag)

        # 渲染配置模板
        configuration['template'] = Sidecar.render_template(configuration['template'], Sidecar.get_variables(node))

        # 返回配置信息和新的 ETag
        return JsonResponse(configuration, headers={'ETag': new_etag})

    @staticmethod
    def get_variables(node_obj):
        """获取变量"""
        objs = SidecarEnv.objects.filter(cloud_region=node_obj.cloud_region_id)
        variables = {obj.key: obj.value for obj in objs}
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
        _variables = {
            **variables,
        }
        template_str = template_str.replace('node.', 'node__')
        template = Template(template_str)
        return template.safe_substitute(variables)

    @staticmethod
    def get_sidecar_install_guide(ip, operating_system, group):
        """生成 sidecar 安装指南"""
        local_host = LOCAL_HOST
        local_api_token = ""
        if operating_system.lower() == 'windows':
            return r'.\install_sidecar.bat  "{}" "{}" "{}" "{}"'.format(ip, local_api_token, local_host, group)
        elif operating_system.lower() == 'linux':
            params = [L_INSTALL_DOWNLOAD_URL, ip, local_api_token, local_host, L_SIDECAR_DOWNLOAD_URL, group]
            return 'curl -sSL {}|bash -s - -n "{}" -t "{}" -s "{}" -d "{}" -g "{}"'.format(*params)
        else:
            return ""

    # def get_installation_steps(self):
    #     """获取安装步骤"""
    #     local_host = LOCAL_HOST
    #     local_api_token = ""
    #
    #     if self.node.os_type == LINUX_OS:
    #         return self.linux_step(self.node.node_id, local_api_token, local_host)
    #     elif self.node.os_type == WINDOWS_OS:
    #         return self.windows_step(self.node.node_id, local_api_token, local_host)

    def windows_step(self, node_id, gl_token, gl_host):
        """windows安装步骤"""

        return [
            {
                "title": "下载安装包",
                "content": "下载安装包",
                "download_url": W_SIDECAR_DOWNLOAD_URL,
            },
            {
                "title": "创建以下目录",
                "content": "c:/gse",
            },
            {
                "title": "执行安装脚本，在指定目录下安装控制器和探针",
                "content": r'.\install_sidecar.bat "{}" "{}" "{}"'.format(node_id, gl_token, gl_host),
            },
        ]

    def linux_step(self, node_id, gl_token, gl_host):
        """linux安装步骤"""

        params = [L_INSTALL_DOWNLOAD_URL, node_id, gl_token, gl_host, L_SIDECAR_DOWNLOAD_URL]
        return [
            {
                "title": "下载安装包",
                "content": 'curl -sSL {}|bash -s - -n "{}" -t "{}" -s "{}" -d "{}"'.format(*params),
            },
        ]
