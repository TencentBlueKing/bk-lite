import os
import uuid
import json

from jinja2 import Environment, FileSystemLoader, DebugUndefined

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.constants.database import DatabaseConstants
from apps.log.constants.plugin import PluginConstants
from apps.log.models import CollectConfig
from apps.rpc.node_mgmt import NodeMgmt

from apps.core.logger import log_logger as logger


class Controller:
    def __init__(self, data):
        self.data = data

    def tls_context(self, node_id):
        context = NodeMgmt().cloudregion_tls_env_by_node_id(node_id)
        return context

    def get_template_info_by_type(self, template_dir: str, type_name: str):
        """
        从指定目录中查找匹配类型的 j2 模板文件，并解析出 type、config_type、file_type。

        :param template_dir: 模板文件所在目录
        :param type_name: 要查找的类型，例如 'cup'
        :return: 列表，每个元素是一个 dict，包含 type/config_type/file_type 三个字段
        """
        result = []
        for filename in os.listdir(template_dir):
            if not filename.endswith('.j2'):
                continue
            parts = filename[:-3].split('.')  # 去掉 .j2 后按 . 分割
            if len(parts) != 3:
                continue  # 忽略非法命名格式
            file_type, config_type, file_type_ext = parts
            if file_type != type_name:
                continue
            result.append({
                "type": file_type,
                "config_type": config_type,
                "file_type": file_type_ext
            })
        return result

    def render_template(self, template_dir: str, file_name: str, context: dict):
        """
        渲染指定目录下的 j2 模板文件。

        :param template_dir: 模板文件所在目录
        :param context: 用于模板渲染的变量字典
        :return: 渲染后的配置字符串
        """
        _context = {**context}
        env = Environment(loader=FileSystemLoader(template_dir), undefined=DebugUndefined)

        # 添加 to_json 过滤器
        env.filters['to_json'] = lambda obj: json.dumps(obj, ensure_ascii=False)

        template = env.get_template(file_name)
        return template.render(_context)

    def format_configs(self):
        """ 格式化配置数据，将实例和配置合并成最终的配置列表。"""
        collect_type = self.data["collect_type"]
        collector = self.data["collector"]
        configs = []
        for instance in self.data["instances"]:
            node_ids = instance.pop("node_ids")
            for node_id in node_ids:
                node_info = {"node_id": node_id}
                for config in self.data["configs"]:
                    _config = {"collector": collector, "collect_type": collect_type, **node_info, **config, **instance}
                    configs.append(_config)
        return configs

    def get_child_config_sort_order(self, collect_type: str):
        """ 获取子配置的排序顺序, 用于配置渲染顺序 """
        sort_order = 1 if collect_type == "flows" else 0
        return sort_order

    def controller(self):
        """
        创建采集配置的控制器方法

        优化点：
        1. 使用 batch_create_configs_and_child_configs 原子性创建配置和子配置
        2. 移除手动回滚逻辑，依赖外层事务自动回滚
        3. 简化错误处理
        """
        base_dir = PluginConstants.DIRECTORY
        configs = self.format_configs()
        node_configs, node_child_configs, collect_configs = [], [], []

        # 步骤1：准备所有配置数据（渲染模板）
        for config_info in configs:
            template_dir = os.path.join(base_dir, config_info["collector"], config_info["collect_type"])
            templates = self.get_template_info_by_type(template_dir, config_info["collect_type"])
            env_config = {k[4:]: v for k, v in config_info.items() if k.startswith("ENV_")}
            tls_context = self.tls_context(config_info["node_id"])

            for template in templates:
                is_child = True if template["config_type"] == "child" else False
                collector_name = config_info["collector"]
                config_id = str(uuid.uuid4().hex)

                # 生成配置
                template_config = self.render_template(
                    template_dir,
                    f"{template['type']}.{template['config_type']}.{template['file_type']}.j2",
                    {**tls_context, **config_info, "config_id": config_id.upper()},
                )

                # 节点管理创建配置
                if is_child:
                    # 子配置环境变量加上config_id作后缀，确保环境变量名为大写
                    child_env_config = {f"{k.upper()}__{config_id.upper()}": v for k, v in env_config.items()}
                    node_child_config = dict(
                        id=config_id,
                        collect_type=config_info["collect_type"],
                        type=config_info["collect_type"],
                        content=template_config,
                        node_id=config_info["node_id"],
                        collector_name=collector_name,
                        env_config=child_env_config,
                        sort_order=self.get_child_config_sort_order(config_info["collect_type"]),
                    )
                    node_child_configs.append(node_child_config)
                else:
                    node_config = dict(
                        id=config_id,
                        name=f'{collector_name}-{config_id}',
                        content=template_config,
                        node_id=config_info["node_id"],
                        collector_name=collector_name,
                        env_config=env_config,
                    )
                    node_configs.append(node_config)

                # 监控记录配置
                collect_configs.append(
                    CollectConfig(
                        id=config_id,
                        collect_instance_id=config_info["instance_id"],
                        file_type=template["file_type"],
                        is_child=is_child,
                    )
                )

        # 步骤2：批量创建 CollectConfig（使用外层事务，不新建事务）
        CollectConfig.objects.bulk_create(collect_configs, batch_size=DatabaseConstants.DEFAULT_BATCH_SIZE)
        logger.info(f"创建 CollectConfig 成功，数量={len(collect_configs)}")

        # 步骤3：原子性创建配置和子配置（RPC调用，底层有事务保护，失败会抛异常）
        if node_configs or node_child_configs:
            NodeMgmt().batch_create_configs_and_child_configs(node_configs, node_child_configs)
            logger.info(f"创建配置成功，node_config={len(node_configs)}个，child_config={len(node_child_configs)}个")

        logger.info(f"创建采集配置成功，共{len(collect_configs)}个配置")

    def render_config_template_content(self, file_type, context_data, instance_id):
        """ 渲染配置模板内容。"""

        template_dir = os.path.join(PluginConstants.DIRECTORY, self.data["collector"], self.data["collect_type"])
        templates = self.get_template_info_by_type(template_dir, self.data["collect_type"])

        template = None

        for _template in templates:
            if _template["config_type"] != file_type:
                continue
            template = _template

        if template is None:
            raise BaseAppException(f"No matching template found for {self.data['collect_type']} with file type {file_type}")

        # 生成配置
        content = self.render_template(
            template_dir,
            f"{template['type']}.{template['config_type']}.{template['file_type']}.j2",
            {"instance_id": instance_id,  **context_data},
        )

        return content
