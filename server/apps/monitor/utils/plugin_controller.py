import ast
import uuid

from jinja2 import Environment, BaseLoader, DebugUndefined

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import CollectConfig, MonitorPluginConfigTemplate
from apps.rpc.node_mgmt import NodeMgmt


def to_toml_dict(d):
    """将字典转换为 TOML 格式的内联表"""
    if not d:
        return "{}"
    return "{ " + ", ".join(f'"{k}" = "{v}"' for k, v in d.items()) + " }"


class Controller:
    def __init__(self, data):
        self.data = data
        # 优化：复用 Jinja2 Environment 对象，避免重复创建
        self._jinja_env = None

    @property
    def jinja_env(self):
        """延迟初始化并缓存 Jinja2 Environment 对象"""
        if self._jinja_env is None:
            self._jinja_env = Environment(loader=BaseLoader(), undefined=DebugUndefined)
            self._jinja_env.filters['to_toml'] = to_toml_dict
        return self._jinja_env

    def get_templates_by_collector(self, collector: str, collect_type: str):
        """
        从数据库中查找指定采集器和采集类型的所有配置模板，按 type 分组。

        :param collector: 采集器名称
        :param collect_type: 采集类型
        :return: 字典，key 为 type，value 为该 type 下的所有模板列表
        """
        templates = MonitorPluginConfigTemplate.objects.filter(
            plugin__collector=collector,
            plugin__collect_type=collect_type
        ).values('type', 'config_type', 'file_type', 'content')

        # 按 type 分组
        templates_by_type = {}
        for template in templates:
            type_name = template['type']
            if type_name not in templates_by_type:
                templates_by_type[type_name] = []
            templates_by_type[type_name].append(template)

        return templates_by_type

    def render_template(self, template_content: str, context: dict):
        """
        渲染模板内容。

        :param template_content: 模板内容字符串
        :param context: 用于模板渲染的变量字典
        :return: 渲染后的配置字符串
        :raises ValueError: 当 instance_id 格式不正确时
        """
        _context = {**context}

        # 安全处理 instance_id 解析
        instance_id = _context.get("instance_id")
        if instance_id:
            try:
                if isinstance(instance_id, str):
                    parsed_id = ast.literal_eval(instance_id)
                    if isinstance(parsed_id, (list, tuple)) and len(parsed_id) > 0:
                        _context.update(instance_id=parsed_id[0])
                    else:
                        logger.warning(f"instance_id 格式异常: {instance_id}")
                elif isinstance(instance_id, (list, tuple)) and len(instance_id) > 0:
                    _context.update(instance_id=instance_id[0])
            except (ValueError, SyntaxError) as e:
                logger.error(f"解析 instance_id 失败: {instance_id}, 错误: {e}")
                raise ValueError(f"无效的 instance_id 格式: {instance_id}") from e

        template = self.jinja_env.from_string(template_content)
        return template.render(_context)

    def format_configs(self):
        """
        格式化配置数据，将实例和配置合并成最终的配置列表。

        :return: 格式化后的配置列表
        :raises KeyError: 当必需的字段缺失时
        """
        try:
            collect_type = self.data["collect_type"]
            collector = self.data["collector"]
            instances = self.data.get("instances", [])
            configs_template = self.data.get("configs", [])
        except KeyError as e:
            logger.error(f"缺少必需的字段: {e}")
            raise ValueError(f"输入数据缺少必需的字段: {e}") from e

        configs = []
        # 修复：避免修改原始数据，使用副本
        for instance in instances:
            # 创建副本，避免修改原始数据
            instance_copy = {**instance}
            node_ids = instance_copy.pop("node_ids", [])

            if not node_ids:
                logger.warning(f"实例 {instance_copy.get('instance_id', 'unknown')} 没有关联节点")
                continue

            for node_id in node_ids:
                node_info = {"node_id": node_id}
                for config in configs_template:
                    _config = {
                        "collector": collector,
                        "collect_type": collect_type,
                        **node_info,
                        **config,
                        **instance_copy
                    }
                    configs.append(_config)

        return configs

    def controller(self):
        """
        创建采集配置的控制器方法

        优化点：
        1. 使用 batch_create_configs_and_child_configs 原子性创建配置和子配置
        2. 移除手动回滚逻辑，依赖外层事务自动回滚
        3. 简化错误处理
        4. 从数据库读取模板而不是从目录扫描
        5. 提前批量查询模板，避免循环中重复查询数据库
        6. 复用 Jinja2 Environment 对象
        7. 避免修改原始数据
        8. 增强输入验证和错误处理

        :raises ValueError: 当输入数据不合法时
        """
        # 输入验证
        if not self.data:
            raise ValueError("输入数据不能为空")

        try:
            collector = self.data["collector"]
            collect_type = self.data["collect_type"]
        except KeyError as e:
            logger.error(f"输入数据缺少必需字段: {e}")
            raise ValueError(f"输入数据缺少必需字段: {e}") from e

        configs = self.format_configs()
        node_configs, node_child_configs, collect_configs = [], [], []

        # 优化：直接从 self.data 获取采集器和采集类型，然后一次性查询所有模板
        templates_by_type = self.get_templates_by_collector(collector, collect_type)

        if not templates_by_type:
            logger.error(f"未找到任何模板：collector={collector}, collect_type={collect_type}")
            return

        if not configs:
            logger.warning(f"没有需要创建的配置：collector={collector}, collect_type={collect_type}")
            return

        # 步骤1：准备所有配置数据（使用预加载的模板渲染）
        for config_info in configs:
            type_name = config_info.get("type")
            if not type_name:
                logger.warning(f"配置缺少 type 字段，跳过: {config_info}")
                continue

            templates = templates_by_type.get(type_name)

            if not templates:
                logger.warning(f"未找到模板：collector={collector}, "
                             f"collect_type={collect_type}, "
                             f"type={type_name}")
                continue

            env_config = {k[4:]: v for k, v in config_info.items() if k.startswith("ENV_")}

            for template in templates:
                is_child = template["config_type"] == "child"
                collector_name = "Telegraf" if is_child else collector
                config_id = str(uuid.uuid4().hex)

                try:
                    template_config = self.render_template(
                        template["content"],
                        {**config_info, "config_id": config_id.upper()},
                    )
                except (ValueError, Exception) as e:
                    logger.error(f"渲染模板失败：type={type_name}, "
                               f"config_id={config_id}, "
                               f"instance_id={config_info.get('instance_id')}, "
                               f"错误: {e}")
                    continue

                if is_child:
                    child_env_config = {f"{k.upper()}__{config_id.upper()}": v for k, v in env_config.items()}
                    node_child_configs.append(dict(
                        id=config_id,
                        collect_type=collect_type,
                        type=config_info["type"],
                        content=template_config,
                        node_id=config_info["node_id"],
                        collector_name=collector_name,
                        env_config=child_env_config,
                    ))
                else:
                    node_configs.append(dict(
                        id=config_id,
                        name=f'{collector_name}-{config_id}',
                        content=template_config,
                        node_id=config_info["node_id"],
                        collector_name=collector_name,
                        env_config=env_config,
                    ))

                collect_configs.append(CollectConfig(
                    id=config_id,
                    collector=collector_name,
                    monitor_instance_id=config_info["instance_id"],
                    collect_type=collect_type,
                    config_type=config_info["type"],
                    file_type=template["file_type"],
                    is_child=is_child,
                ))

        if not collect_configs:
            logger.warning(f"没有生成任何配置：collector={collector}, collect_type={collect_type}")
            return

        # 步骤2：批量创建 CollectConfig（使用外层事务，不新建事务）
        try:
            CollectConfig.objects.bulk_create(collect_configs, batch_size=DatabaseConstants.COLLECT_CONFIG_BATCH_SIZE)
            logger.info(f"创建 CollectConfig 成功，数量={len(collect_configs)}")
        except Exception as e:
            logger.error(f"批量创建 CollectConfig 失败：{e}")
            raise

        # 步骤3：原子性创建配置和子配置（RPC调用，底层有事务保护，失败会抛异常）
        if node_configs or node_child_configs:
            try:
                NodeMgmt().batch_create_configs_and_child_configs(node_configs, node_child_configs)
                logger.info(f"创建配置成功，node_config={len(node_configs)}个，child_config={len(node_child_configs)}个")
            except Exception as e:
                logger.error(f"RPC 调用失败，配置创建失败：node_configs={len(node_configs)}, "
                           f"child_configs={len(node_child_configs)}, 错误: {e}")
                raise

        logger.info(f"创建采集配置成功，共{len(collect_configs)}个配置")
