import asyncio
import importlib
import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.logger import logger, safe_log_value
from core.plugin.source_resolver import PluginResolution
from core.plugin.yaml_reader import ExecutorConfig


@dataclass(frozen=True)
class PreparedPluginExecutorFactory:
    """Run 级静态执行计划；目标级只复制参数并构造 Collector 实例。"""

    model: str
    executor_config: ExecutorConfig
    plugin_resolution: Optional[PluginResolution]
    fallback_executor_config: Optional[ExecutorConfig]
    strict_enterprise: bool
    collector_class: type

    def __call__(self, params: Dict[str, Any]) -> "PluginExecutor":
        return PluginExecutor(
            self.model,
            self.executor_config,
            params,
            plugin_resolution=self.plugin_resolution,
            fallback_executor_config=self.fallback_executor_config,
            strict_enterprise=self.strict_enterprise,
            collector_class=self.collector_class,
        )


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
        strict_enterprise: bool = False,
        collector_class: type | None = None,
    ):
        self.model = model
        self.params = params
        self.executor_config = executor_config
        self.plugin_resolution = plugin_resolution
        self.fallback_executor_config = fallback_executor_config
        self.strict_enterprise = strict_enterprise
        self._collector_class = collector_class

    @classmethod
    async def prepare(
        cls,
        model: str,
        executor_config: ExecutorConfig,
        *,
        plugin_resolution: Optional[PluginResolution] = None,
        fallback_executor_config: Optional[ExecutorConfig] = None,
        strict_enterprise: bool = False,
    ) -> PreparedPluginExecutorFactory:
        """在目标调度前解析一次 Collector 类，同时保留每目标独立实例。"""
        executor = cls(
            model,
            executor_config,
            {},
            plugin_resolution=plugin_resolution,
            fallback_executor_config=fallback_executor_config,
            strict_enterprise=strict_enterprise,
        )
        collector_info = executor.executor_config.get_collector_info()
        collector_class = await asyncio.to_thread(executor._load_collector_with_fallback, collector_info)
        used_oss_fallback = executor.executor_config is fallback_executor_config
        return PreparedPluginExecutorFactory(
            model=model,
            executor_config=executor.executor_config,
            plugin_resolution=None if used_oss_fallback else plugin_resolution,
            fallback_executor_config=None if used_oss_fallback else fallback_executor_config,
            strict_enterprise=strict_enterprise,
            collector_class=collector_class,
        )

    async def execute(self) -> Dict[str, Any]:
        """
        执行采集 - 统一的执行流程

        Returns:
            采集结果
        """
        source = self.plugin_resolution.source if self.plugin_resolution else "oss"
        logger.debug(
            "event=plugin_executor_started model_id=%s executor=%s source=%s target=%s",
            self.model,
            self.executor_config.executor_type,
            source,
            self.params.get("host") or self.params.get("ip") or "logical",
        )

        collector_instance = await self._prepare_collector()
        # 所有注册插件必须暴露异步契约；同步 SDK 由插件自身用 to_thread 包装。
        return await collector_instance.list_all_resources()

    async def probe(self) -> AccessProbeResult:
        """执行插件声明的最小协议预检；未声明时不得伪造 READY。"""
        collector_instance = await self._prepare_collector()
        if inspect.getattr_static(collector_instance, "probe", None) is None:
            return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)
        probe = getattr(collector_instance, "probe", None)
        if probe is None:
            return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)
        result = await probe()
        if not isinstance(result, AccessProbeResult):
            raise TypeError("collector probe must return AccessProbeResult")
        logger.debug(
            "Access probe finished: status=%s error_code=%s host=%s",
            result.status.value,
            result.error_code or "-",
            self.params.get("host") or self.params.get("ip") or "-",
        )
        return result

    async def _prepare_collector(self):
        collector_class = self._collector_class
        if collector_class is None:
            collector_info = self.executor_config.get_collector_info()
            logger.debug(
                "Loading collector: %s.%s",
                safe_log_value(collector_info["module"]),
                safe_log_value(collector_info["class"]),
            )
            collector_class = await asyncio.to_thread(self._load_collector_with_fallback, collector_info)
        collector_params = dict(self.params)
        trusted_options = (self.executor_config.config.get("collector") or {}).get("options", {})
        if not isinstance(trusted_options, Mapping):
            raise ValueError("collector.options must be a mapping")
        collector_params["_collector_options"] = dict(trusted_options)
        if self.executor_config.is_job:
            os_type = self._determine_os_type()
            script_path = self.executor_config.get_script_path(os_type)
            if not script_path:
                raise ValueError(f"Script not found for os_type '{os_type}'. " f"Available: {self.executor_config.list_available_os()}")
            collector_params["script_path"] = script_path
            logger.debug("Script path: %s", safe_log_value(script_path, max_length=255))
        return await asyncio.to_thread(collector_class, collector_params)

    def _determine_os_type(self) -> str:
        """
        确定操作系统类型

        优先级：
        1. 参数中指定的 os_type
        2. 从节点信息中获取 operating_system
        3. 使用默认值 default_script
        """
        # 优先从参数获取
        if "os_type" in self.params:
            return self.params["os_type"]

        # 从节点信息获取
        node_info = self.params.get("node_info", {})
        if node_info and "operating_system" in node_info:
            os_type = node_info["operating_system"].lower()
            # 映射操作系统名称
            if os_type in ["windows", "win"]:
                return "windows"
            else:
                return "linux"

        # 使用默认值
        return self.executor_config.config.get("default_script", "linux")

    @staticmethod
    def _load_collector(module_name: str, class_name: str):
        """动态加载采集器类"""
        module = importlib.import_module(module_name)
        collector_class = getattr(module, class_name)
        logger.debug(
            "Collector loaded: %s.%s",
            safe_log_value(module_name),
            safe_log_value(class_name),
        )
        return collector_class

    def _load_collector_with_fallback(self, collector_info: Dict[str, str]):
        try:
            return self._load_collector(collector_info["module"], collector_info["class"])
        except Exception as exc:
            if not self.plugin_resolution or self.plugin_resolution.source != "enterprise":
                raise

            if self.strict_enterprise:
                logger.error(
                    "event=plugin_enterprise_load_failed model_id=%s selected_source=enterprise "
                    "strict=true failed_stage=run_preparation error_type=%s",
                    safe_log_value(self.model),
                    type(exc).__name__,
                )
                raise

            if not self.plugin_resolution.has_oss_fallback or not self.fallback_executor_config:
                raise

            logger.warning(
                "event=plugin_fallback model_id=%s failed_source=enterprise " "fallback_source=oss failed_stage=run_preparation error_type=%s",
                safe_log_value(self.model),
                type(exc).__name__,
            )

            self.executor_config = self.fallback_executor_config
            fallback_collector_info = self.executor_config.get_collector_info()
            logger.debug(
                "event=plugin_fallback_load_started module=%s class=%s",
                safe_log_value(fallback_collector_info["module"]),
                safe_log_value(fallback_collector_info["class"]),
            )
            return self._load_collector(fallback_collector_info["module"], fallback_collector_info["class"])
