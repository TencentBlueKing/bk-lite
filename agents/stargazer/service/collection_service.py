"""采集服务 V2 - 基于 YAML 配置的新版本采集服务"""

import asyncio
import importlib
import json
import ntpath
import posixpath
from typing import Any, Dict, Optional

from core.collection.contracts import AccessProbeResult, StructuredMetricsPayload
from core.logger import logger
from core.plugin.error_logging import log_plugin_exception, should_log_plugin_exception
from core.plugin.executor import PluginExecutor
from core.plugin.yaml_reader import yaml_reader
from plugins.base_utils import convert_to_prometheus_format


class PreparedCollectionServiceFactory:
    """一次 Run 共享静态执行计划；调用时仍创建目标隔离的 Service。"""

    def __init__(self, executor_factory) -> None:
        self._executor_factory = executor_factory

    @property
    def executor_config(self):
        """返回 Collector fallback 后最终采用的执行器配置。"""

        return self._executor_factory.executor_config

    def __call__(self, params: dict):
        return CollectionService(
            params,
            prepared_executor_factory=self._executor_factory,
        )


class CollectionService:
    """
    采集服务 - 基于 YAML 配置的新架构

    设计说明：
    - 统一运行时按 IP 调度，每个 CollectionService 实例只处理单个 host（或无 host）
    - host字段可能为None（云采集使用默认endpoint）
    - 不在服务内部并发；跨 IP 并发由统一异步运行时控制

    工作流程：
    1. 根据 plugin_name 推断 model（或直接传入 model）
    2. 读取 plugins/inputs/{model}/plugin.yml
    3. 确定执行器类型（job/protocol）
    4. 通过 PluginExecutor 执行单次采集
    """

    def __init__(
        self,
        params: Optional[dict] = None,
        *,
        config_provider=None,
        prepared_executor_factory=None,
    ):
        self.yaml_reader = config_provider or yaml_reader
        # 运行期会补充 node_info/script_path，不能污染 HTTP 请求或其他目标复用的参数。
        self.params = dict(params or {})
        self.plugin_name = self.params.pop("plugin_name", None)
        self.model_id = self.params["model_id"]
        self.host = self.params.get("host")  # 可能为None（云采集）
        self._prepared_executor_factory = prepared_executor_factory

    @classmethod
    async def prepare(
        cls,
        params: dict,
        *,
        config_provider=None,
    ) -> PreparedCollectionServiceFactory:
        """在目标入队前完成 YAML 来源解析和 Collector 类加载。"""
        run_params = dict(params)
        model_id = run_params["model_id"]
        executor_type = run_params["executor_type"]
        prefer_enterprise = cls._get_bool_param(run_params, "prefer_enterprise", True)
        strict_enterprise = cls._get_bool_param(run_params, "strict_enterprise", False)
        provider = config_provider or yaml_reader
        resolved_executor = await provider.get_executor_config_with_resolution_async(
            model_id,
            executor_type,
            prefer_enterprise=prefer_enterprise,
        )
        executor_factory = await PluginExecutor.prepare(
            model_id,
            resolved_executor.executor_config,
            plugin_resolution=resolved_executor.plugin_resolution,
            fallback_executor_config=resolved_executor.fallback_executor_config,
            strict_enterprise=strict_enterprise,
        )
        return PreparedCollectionServiceFactory(executor_factory)

    @staticmethod
    def _get_bool_param(params: Dict[str, Any], key: str, default: bool) -> bool:
        value = params.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _is_config_file_callback(self) -> bool:
        plugin_name = str(self.plugin_name or "")
        model_id = str(self.model_id or "")
        return (
            str(self.params.get("callback_subject") or "") == "receive_config_file_result"
            or plugin_name in {"config_file_info", "network_config_file_info"}
            or model_id in {"config_file", "network_config_file"}
        )

    def _get_callback_instance_name(self) -> str:
        return str(self.params.get("host") or self.params.get("instance_name") or "")

    def _get_callback_instance_uuid(self) -> str:
        return str(self.params.get("target_instance_uuid") or "")

    def _get_callback_model_id(self) -> str:
        return str(self.params.get("target_model_id") or self.params.get("model_id") or "host")

    @staticmethod
    def _extract_file_name(file_path: str) -> str:
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return ""
        if ":\\" in normalized_path or "\\" in normalized_path:
            return ntpath.basename(normalized_path)
        return posixpath.basename(normalized_path)

    async def collect(self):
        """
        单次采集方法

        Returns:
            采集结果（Prometheus 格式字符串 或 字典）
        """
        try:
            # 根据参数确定执行器类型（job 或 protocol）
            executor_type = self.params["executor_type"]
            instance_id = self.params.get("instance_id", "")
            logger.debug(
                "start collect.  instance_id=%s task_id=%s model_id=%s plugin_name=%s target=%s executor=%s",
                instance_id,
                self.params.get("collection_task_id") or "-",
                self.model_id,
                self.plugin_name or "-",
                self.host or "logical",
                executor_type,
            )

            if self._prepared_executor_factory is not None:
                executor = self._prepared_executor_factory(self.params)
            else:
                prefer_enterprise = self._get_bool_param(self.params, "prefer_enterprise", True)
                strict_enterprise = self._get_bool_param(self.params, "strict_enterprise", False)

                # 插件来源解析入口：先判断 enterprise 能力是否可用，再按
                # enterprise/plugins/inputs/{model}/plugin.yml -> plugins/inputs/{model}/plugin.yml
                # 的顺序选中最终 plugin.yml；若命中 enterprise 且后续 import 失败，executor 会按 strict_enterprise
                # 决定是直接报错还是回退到同名 oss 插件。
                resolved_executor = await self.yaml_reader.get_executor_config_with_resolution_async(
                    self.model_id,
                    executor_type,
                    prefer_enterprise=prefer_enterprise,
                )
                executor = PluginExecutor(
                    self.model_id,
                    resolved_executor.executor_config,
                    self.params,
                    plugin_resolution=resolved_executor.plugin_resolution,
                    fallback_executor_config=resolved_executor.fallback_executor_config,
                    strict_enterprise=strict_enterprise,
                )
            result = await executor.execute()

            if self.params.get("callback_subject"):
                return (
                    result.get("result", {})
                    if result.get("success")
                    else (
                        {
                            "collect_task_id": self.params.get("collect_task_id"),
                            "execution_id": self.params.get("execution_id"),
                            "protocol_version": self.params.get("protocol_version"),
                            "instance_uuid": self._get_callback_instance_uuid(),
                            "instance_name": self._get_callback_instance_name(),
                            "model_id": self._get_callback_model_id(),
                            "file_path": self.params.get("config_file_path", ""),
                            "file_name": self._extract_file_name(self.params.get("config_file_path", "")),
                            "version": "",
                            "status": "error",
                            "size": 0,
                            "error": result.get("result", {}).get(
                                "cmdb_collect_error",
                                result.get("error", "Unknown error"),
                            ),
                            "content_base64": "",
                        }
                        if self._is_config_file_callback()
                        else {
                            "collect_task_id": self.params.get("collect_task_id"),
                            "execution_id": self.params.get("execution_id"),
                            "instance_id": self.params.get("instance_id") or self.host or "",
                            "model_id": self.params.get("target_model_id") or self.params.get("model_id"),
                            "file_path": self.params.get("config_file_path", ""),
                            "file_name": self._extract_file_name(self.params.get("config_file_path", "")),
                            "version": "",
                            "status": "error",
                            "size": 0,
                            "error": result.get("result", {}).get(
                                "cmdb_collect_error",
                                result.get("error", "Unknown error"),
                            ),
                            "content_base64": "",
                        }
                    )
                )

            processed = await asyncio.to_thread(self._process_result, result)
            if self.params.get("_runtime_structured_metrics"):
                result_data = result.get("result", {})
                error = ""
                if not result.get("success", True):
                    error = str(result_data.get("cmdb_collect_error", result.get("error", "Unknown error")))
                final_result = StructuredMetricsPayload(
                    data=processed,
                    error=error,
                    round_metadata=self._extract_round_metadata(result),
                )
            else:
                final_result = await asyncio.to_thread(convert_to_prometheus_format, processed)

            return final_result

        except FileNotFoundError as error:
            self._log_plugin_exception(error)
            return self._generate_error_response(f"Plugin config not found for model '{self.model_id}'")

        except Exception as e:
            self._log_plugin_exception(e)
            return self._generate_error_response(str(e))

    def _log_plugin_exception(self, error: BaseException) -> None:
        if not should_log_plugin_exception(self.params):
            return
        log_plugin_exception(
            logger,
            error=error,
            task_id=self.params.get("collection_task_id"),
            plugin_ref=self.params.get("collection_plugin_ref"),
            model_id=self.model_id,
            plugin_name=self.plugin_name,
            target=self.host,
        )

    async def probe(self) -> AccessProbeResult:
        """通过当前解析出的协议 Adapter 执行最小凭据感知预检。"""
        if self._prepared_executor_factory is not None:
            return await self._prepared_executor_factory(self.params).probe()
        executor_type = self.params["executor_type"]
        prefer_enterprise = self._get_bool_param(self.params, "prefer_enterprise", True)
        strict_enterprise = self._get_bool_param(self.params, "strict_enterprise", False)
        resolved_executor = await self.yaml_reader.get_executor_config_with_resolution_async(
            self.model_id,
            executor_type,
            prefer_enterprise=prefer_enterprise,
        )
        executor = PluginExecutor(
            self.model_id,
            resolved_executor.executor_config,
            self.params,
            plugin_resolution=resolved_executor.plugin_resolution,
            fallback_executor_config=resolved_executor.fallback_executor_config,
            strict_enterprise=strict_enterprise,
        )
        return await executor.probe()

    def _format_result(self, result: Dict[str, Any]) -> str:
        """在线程中完成可能随结果规模增长的转换，保持事件循环只负责编排。"""
        return convert_to_prometheus_format(self._process_result(result))

    def _process_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单次采集结果

        为采集结果添加必要的元数据字段（host、collect_status等）
        """
        processed = {}

        # 处理采集失败的情况
        if not result.get("success", True):
            # 提取错误信息
            result_data = result.get("result", {})
            error_msg = result_data.get("cmdb_collect_error", result.get("error", "Unknown error"))

            # 创建错误记录
            error_record = {
                "collect_status": "failed",
                "collect_error": error_msg,
                "bk_obj_id": self.model_id,
            }
            if self.host:
                error_record["host"] = self.host

            processed[self.model_id] = [error_record]
            return processed

        # 处理采集成功的情况
        result_data = result.get("result", {})
        for model_id, items in result_data.items():
            if model_id not in processed:
                processed[model_id] = []
            if not items:
                # 空结果也标记为成功
                processed[model_id].append(
                    {
                        "bk_obj_id": model_id,
                        "collect_status": "success",
                    }
                )
                self._encode_winsphere_metric_labels(processed[model_id][-1])
                continue

            # 为每个item添加状态和host标签
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        if self.host:
                            item["host"] = self.host
                        item["bk_obj_id"] = model_id
                        item.setdefault("collect_status", "success")
                        self._strip_snapshot_transport_fields(item)
                        self._encode_winsphere_metric_labels(item)
                processed[model_id].extend(items)
            elif isinstance(items, dict):
                # 单个字典的情况
                if self.host:
                    items["host"] = self.host
                items["collect_status"] = "success"
                items["bk_obj_id"] = model_id
                self._strip_snapshot_transport_fields(items)
                self._encode_winsphere_metric_labels(items)
                processed[model_id].append(items)

        return processed

    @staticmethod
    def _strip_snapshot_transport_fields(item):
        for key in (
            "snapshot_id",
            "snapshot_status",
            "snapshot_manifest",
            "software_snapshot_status",
            "software_expected_count",
            "software_error_count",
        ):
            item.pop(key, None)

    def _extract_round_metadata(self, result):
        if self.model_id not in {"pc", "winsphere"} or not result.get("success", True):
            return None
        snapshot_id = str(result.get("snapshot_id") or "").strip()
        snapshot_status = str(result.get("snapshot_status") or "").strip()
        if not snapshot_id or snapshot_status not in {"complete", "partial"}:
            return None
        details = dict(result.get("snapshot_metadata") or {})
        if self.model_id == "winsphere":
            details["snapshot_manifest"] = result.get("snapshot_manifest")
        return {
            "snapshot_id": snapshot_id,
            "snapshot_status": snapshot_status,
            "details": details,
        }

    def _encode_winsphere_metric_labels(self, item):
        """仅在 Prometheus 传输边界编码 WinSphere 的结构化标签。"""
        if self.model_id != "winsphere":
            return
        for key, value in list(item.items()):
            if isinstance(value, (list, dict)):
                item[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

    def _generate_error_response(self, error_message: str):
        if self.params.get("_runtime_structured_metrics"):
            return StructuredMetricsPayload(data={}, error=error_message)
        if self.model_id == "winsphere":
            processed = self._process_result(
                {
                    "success": False,
                    "result": {
                        "cmdb_collect_error": error_message,
                    },
                }
            )
            return convert_to_prometheus_format(processed)
        return {"status": "failed", "error": error_message}

    async def list_regions(self):
        """异步边界：云 SDK 的区域查询整体在线程中执行。"""
        return await asyncio.to_thread(self._list_regions_sync)

    def _list_regions_sync(self):
        """
        列出区域（保留向后兼容接口）

        注意：此方法主要用于云平台插件
        """
        if not self.model_id:
            return {"result": [], "success": False, "message": "model_id is required"}

        try:
            resolved_executor = self.yaml_reader.get_executor_config_with_resolution(self.model_id, "protocol")
            executor_config = resolved_executor.executor_config

            # 只有 protocol 类型支持 list_regions
            if not executor_config.is_cloud_protocol:
                logger.warning(f"list_regions not supported for executor type: {executor_config.executor_type}")
                return {
                    "result": [],
                    "success": False,
                    "message": f"list_regions not supported for executor type: {executor_config.executor_type}",
                }

            # 加载采集器
            collector_info = executor_config.get_collector_info()
            module = importlib.import_module(collector_info["module"])
            plugin_class = getattr(module, collector_info["class"])

            # 实例化并调用
            plugin_instance = plugin_class(self.params or {})
            result = plugin_instance.list_regions()

            if isinstance(result, list):
                return {
                    "result": result,
                    "success": True,
                    "message": "",
                }

            return {
                "result": result.get("data", []),
                "success": result.get("result", False),
                "message": result.get("message", ""),
            }

        except Exception as e:  # noqa
            import traceback

            logger.error(f"Error list_regions for {self.plugin_name or self.model_id}: {traceback.format_exc()}")
            return {"result": [], "success": False, "message": str(e)}
