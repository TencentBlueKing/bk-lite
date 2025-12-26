"""YAML 配置读取器"""
import os.path

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from sanic.log import logger


@dataclass
class ExecutorConfig:
    """执行器配置"""
    executor_type: str  # job 或 protocol
    config: Dict[str, Any]
    plugin_config: Dict[str, Any]

    @property
    def is_job(self) -> bool:
        """是否是 job 类型"""
        return self.executor_type == 'job'

    @property
    def is_protocol(self) -> bool:
        """是否是 protocol 类型"""
        return self.executor_type == 'protocol'

    @property
    def is_cloud_protocol(self) -> bool:
        """是否是云协议采集器（protocol 类型下）"""
        return self.plugin_config["metadata"].get('cloud_protocol', False)

    def get_timeout(self) -> int:
        """获取超时时间"""
        return self.config.get('timeout', 60)

    # Job 相关方法
    def get_script_path(self, os_type: str) -> Optional[str]:
        """
        获取脚本路径（job 类型）
        
        Args:
            os_type: linux 或 windows
        
        Returns:
            脚本文件路径
        """
        if not self.is_job:
            return None

        scripts = self.config.get('scripts', {})

        # 先找指定的 os_type
        if os_type in scripts:
            return scripts[os_type]

        # 找不到，使用默认
        default_script = self.config.get('default_script', 'linux')
        return scripts.get(default_script)

    def list_available_os(self) -> list:
        """列出支持的操作系统（job 类型）"""
        if not self.is_job:
            return []
        return list(self.config.get('scripts', {}).keys())

    # Protocol 相关方法
    def get_collector_info(self) -> Dict[str, str]:
        """
        获取采集器信息
        
        对于 Protocol 类型：从配置中读取 collector 信息
        对于 Job 类型：优先从配置读取，否则使用默认的 SSHPlugin
        
        Returns:
            包含 module 和 class 的字典
        """
        collector = self.config.get('collector', {})

        # 如果配置了 collector，直接使用
        if collector and collector.get('module') and collector.get('class'):
            return {
                'module': collector.get('module'),
                'class': collector.get('class')
            }

        # 否则根据类型返回默认值
        if self.is_protocol:
            raise ValueError(f"Protocol executor requires 'collector' configuration")
        elif self.is_job:
            # Job 类型默认使用 SSHPlugin
            return {
                'module': 'plugins.script_executor',
                'class': 'SSHPlugin'
            }
        else:
            raise ValueError(f"Unknown executor type: {self.executor_type}")


class PluginYamlReader:
    """插件 YAML 读取器"""

    def __init__(self, plugins_base_dir: str = "plugins/inputs"):
        self.plugins_base_dir = Path(plugins_base_dir)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def read_plugin_config(self, model: str) -> Dict[str, Any]:
        """
        读取插件配置
        
        Args:
            model: 模型名称，如 'mysql', 'vmware_vc'
        
        Returns:
            插件配置字典
        """
        # 检查缓存
        if model in self._cache:
            logger.debug(f"Using cached config for: {model}")
            return self._cache[model]

        # 构建配置文件路径
        config_path = os.path.join(self.plugins_base_dir, model, "plugin.yml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Plugin config not found: {config_path}")

        # 读取 YAML
        logger.info(f"Loading plugin config: {config_path}")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 缓存
        self._cache[model] = config

        return config

    def get_executor_config(self, model: str, executor_type: str) -> ExecutorConfig:
        """
        获取执行器配置
        
        Args:
            model: 模型名称，如 'mysql', 'vmware_vc'
            executor_type: 执行器类型，'job' 或 'protocol'
        
        Returns:
            ExecutorConfig 对象
        """
        # 读取插件配置
        plugin_config = self.read_plugin_config(model)

        # 获取执行器配置
        executors = plugin_config.get('executors', {})

        if executor_type not in executors:
            # 尝试使用默认执行器
            default_executor = plugin_config.get('default_executor')
            if default_executor and default_executor in executors:
                logger.info(f"Executor '{executor_type}' not found, using default: {default_executor}")
                executor_type = default_executor
            else:
                raise ValueError(
                    f"Executor type '{executor_type}' not found in plugin '{model}'. "
                    f"Available: {list(executors.keys())}"
                )

        executor_data = executors[executor_type]

        return ExecutorConfig(
            executor_type=executor_type,
            config=executor_data,
            plugin_config=plugin_config
        )

    def list_executors(self, model: str) -> list:
        """列出插件的所有执行器"""
        config = self.read_plugin_config(model)
        return list(config.get('executors', {}).keys())

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()


# 全局实例
yaml_reader = PluginYamlReader()
