import importlib
import inspect
from typing import Dict, Any
from sanic.log import logger
from core.yaml_reader import ExecutorConfig


class PluginExecutor:
    """
    插件执行器 - 统一的执行逻辑
    
    无论是 Job 还是 Protocol，都通过加载采集器类并调用 list_all_resources 方法来执行
    """

    def __init__(self, model: str, executor_config: ExecutorConfig, params: Dict[str, Any]):
        self.model = model
        self.params = params
        self.executor_config = executor_config

    async def execute(self) -> Dict[str, Any]:
        """
        执行采集 - 统一的执行流程
        
        Returns:
            采集结果
        """
        logger.info(f"Executing plugin: model_id={self.model}, executor={self.executor_config.executor_type}")

        # 1. 获取采集器信息
        collector_info = self.executor_config.get_collector_info()
        logger.info(f" Loading collector: {collector_info['module']}.{collector_info['class']}")

        # 2. 动态加载采集器
        collector_class = self._load_collector(collector_info['module'], collector_info['class'])

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

        # 检查 list_all_resources 是否是协程函数
        if inspect.iscoroutinefunction(collector_instance.list_all_resources):
            result = await collector_instance.list_all_resources()
        else:
            result = collector_instance.list_all_resources()

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
