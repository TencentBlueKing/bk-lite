import ast
import os
import uuid

from jinja2 import Environment, FileSystemLoader, DebugUndefined
from apps.monitor.models import CollectConfig
from apps.rpc.node_mgmt import NodeMgmt


def to_toml_dict(d):
    if not d:
        return "{}"
    return "{ " + ", ".join(f'"{k}" = "{v}"' for k, v in d.items()) + " }"


class Controller:
    def __init__(self, data):
        self.data = data

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
        _context.update(instance_id=ast.literal_eval(_context["instance_id"])[0])

        env = Environment(loader=FileSystemLoader(template_dir), undefined=DebugUndefined)
        env.filters['to_toml'] = to_toml_dict

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

    def controller(self):
        base_dir = "apps/monitor/plugins"
        configs = self.format_configs()
        node_configs, node_child_configs, collect_configs = [], [], []
        for config_info in configs:
            template_dir = os.path.join(base_dir, config_info["collector"], config_info["collect_type"], config_info["instance_type"])
            templates = self.get_template_info_by_type(template_dir, config_info["type"])
            env_config = {k[4:]: v for k, v in config_info.items() if k.startswith("ENV_")}

            for template in templates:
                is_child = True if template["config_type"] == "child" else False
                collector_name = "Telegraf" if is_child else config_info["collector"]
                config_id = str(uuid.uuid4().hex)

                # 生成配置
                template_config = self.render_template(
                    template_dir,
                    f"{template['type']}.{template['config_type']}.{template['file_type']}.j2",
                    {**config_info, "config_id": config_id.upper()},
                )

                # 节点管理创建配置
                if is_child:
                    # 子配置环境变量加上config_id作后缀，确保环境变量名为大写
                    child_env_config = {f"{k.upper()}__{config_id.upper()}": v for k, v in env_config.items()}

                    node_child_config = dict(
                        id=config_id,
                        collect_type=config_info["collect_type"],
                        type=config_info["type"],
                        content=template_config,
                        node_id=config_info["node_id"],
                        collector_name=collector_name,
                        env_config=child_env_config,
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
                        collector=collector_name,
                        monitor_instance_id=config_info["instance_id"],
                        collect_type=config_info["collect_type"],
                        config_type=config_info["type"],
                        file_type=template["file_type"],
                        is_child=is_child,
                    )
                )

        # 记录实例与配置的关系
        CollectConfig.objects.bulk_create(collect_configs, batch_size=100)
        # 创建配置
        NodeMgmt().batch_add_node_config(node_configs)
        # 创建子配置
        NodeMgmt().batch_add_node_child_config(node_child_configs)
