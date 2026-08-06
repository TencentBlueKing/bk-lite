import importlib
from typing import Any, Dict, Optional

from sanic.log import logger

from core.plugin_source_resolver import PluginResolution
from core.yaml_reader import ExecutorConfig


class PluginExecutor:
    """
    插件执行器 - 统一的执行逻辑
    
    无论是 Job 还是 Protocol，都通过加载采集器类并调用 list_all_resources 方法来执行
    """

    def __init__(
        self,
        model: str,
        executor_config: ExecutorConfig,
        params: Dict[str, Any],
        plugin_resolution: Optional[PluginResolution] = None,
        fallback_executor_config: Optional[ExecutorConfig] = None,
        strict_enterprise: bool = False
    ):
        self.model = model
        self.params = params
        self.executor_config = executor_config
        self.plugin_resolution = plugin_resolution
        self.fallback_executor_config = fallback_executor_config
        self.strict_enterprise = strict_enterprise

    async def execute(self) -> Dict[str, Any]:
        """
        执行采集 - 统一的执行流程
        
        Returns:
            采集结果
        """
        source = self.plugin_resolution.source if self.plugin_resolution else 'oss'
        logger.info(
            f'Executing plugin: model_id={self.model}, executor={self.executor_config.executor_type}, source={source}'
        )

        # 1. 获取采集器信息
        collector_info = self.executor_config.get_collector_info()
        logger.info(f" Loading collector: {collector_info['module']}.{collector_info['class']}")

        # 2. 动态加载采集器
        collector_class = self._load_collector_with_fallback(collector_info)

        # 3. 为 Job 类型添加脚本路径参数 linux和win的脚本路径不一样
        if self.executor_config.is_job:
            os_type = self._determine_os_type()
            script_path = self.executor_config.get_script_path(os_type)
            if not script_path:
                raise ValueError(
                    f"Script not found for os_type '{os_type}'. Available: {self.executor_config.list_available_os()}"
                )
            self.params['script_path'] = script_path
            logger.info(f"Script path: {script_path}")

        # 4. 实例化采集器
        collector_instance = collector_class(self.params)

        # 5. 执行采集
        logger.info(f"⏳ Executing collection...")

        # 所有注册插件必须暴露异步契约；同步 SDK 由插件自身用 to_thread 包装。
        result = await collector_instance.list_all_resources()

        logger.info(f"✅ Collection completed")
        return result

    def _determine_os_type(self) -> str:
        """
        确定操作系统类型
        
        优先级：
        1. 参数中指定的 os_type
        2. 从节点信息中获取 operating_system
        3. 使用默认值 default_script
        """
        # 优先从参数获取
        if 'os_type' in self.params:
            return self.params['os_type']

        # 从节点信息获取
        node_info = self.params.get('node_info', {})
        if node_info and 'operating_system' in node_info:
            os_type = node_info['operating_system'].lower()
            # 映射操作系统名称
            if os_type in ['windows', 'win']:
                return 'windows'
            else:
                return 'linux'

        # 使用默认值
        return self.executor_config.config.get('default_script', 'linux')

    @staticmethod
    def _load_collector(module_name: str, class_name: str):
        """动态加载采集器类"""
        try:
            module = importlib.import_module(module_name)
            collector_class = getattr(module, class_name)
            logger.info(f"✅ Collector loaded: {module_name}.{class_name}")
            return collector_class
        except Exception as e:
            logger.error(f"❌ Failed to load collector: {e}")
            raise

    def _load_collector_with_fallback(self, collector_info: Dict[str, str]):
        try:
            return self._load_collector(collector_info['module'], collector_info['class'])
        except Exception as exc:
            if not self.plugin_resolution or self.plugin_resolution.source != 'enterprise':
                raise

            if self.strict_enterprise:
                logger.error(
                    f'Strict enterprise mode enabled: model_id={self.model}, selected_source=enterprise, '
                    f'strict=true, failure_reason={exc}'
                )
                raise

            if not self.plugin_resolution.has_oss_fallback or not self.fallback_executor_config:
                raise

            logger.warning(
                f'Plugin fallback triggered: model_id={self.model}, failed_source=enterprise, '
                f'fallback_source=oss, failure_reason={exc}'
            )

            self.executor_config = self.fallback_executor_config
            fallback_collector_info = self.executor_config.get_collector_info()
            logger.info(
                f"Retry loading fallback collector: {fallback_collector_info['module']}.{fallback_collector_info['class']}"
            )
            return self._load_collector(fallback_collector_info['module'], fallback_collector_info['class'])
