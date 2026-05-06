"""采集服务 V2 - 基于 YAML 配置的新版本采集服务"""

import importlib
import json
import ntpath
import posixpath
import time
import traceback
from typing import Dict, Any, Optional
from sanic.log import logger

from core.nats_utils import nats_request
from core.yaml_reader import yaml_reader
from core.plugin_executor import PluginExecutor
from plugins.base_utils import convert_to_prometheus_format


class CollectionService:
    """
    采集服务 - 基于 YAML 配置的新架构

    设计说明：
    - API层已完成IP拆分，每个CollectionService实例只处理单个host（或无host）
    - host字段可能为None（云采集使用默认endpoint）
    - 不再需要内部并发，并发在Worker Pool层实现

    工作流程：
    1. 根据 plugin_name 推断 model（或直接传入 model）
    2. 读取 plugins/inputs/{model}/plugin.yml
    3. 确定执行器类型（job/protocol）
    4. 通过 PluginExecutor 执行单次采集
    """

    def __init__(self, params: Optional[dict] = None):
        self._node_info = None  # 单个节点信息
        self.namespace = "bklite"
        self.yaml_reader = yaml_reader
        self.params = params
        self.plugin_name = self.params.pop("plugin_name", None)
        self.model_id = self.params["model_id"]
        self.host = self.params.get("host")  # 可能为None（云采集）
        self.connect_ip = self.params.get("connect_ip") or self.host

    @staticmethod
    def _get_bool_param(params: Dict[str, Any], key: str, default: bool) -> bool:
        value = params.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _is_config_file_callback(self) -> bool:
        return (
            str(self.params.get("callback_subject") or "") == "receive_config_file_result"
            or str(self.plugin_name or "") == "config_file_info"
            or str(self.model_id or "") == "config_file"
        )

    def _get_callback_instance_name(self) -> str:
        return str(self.params.get("host") or self.params.get("instance_name") or "")

    def _get_callback_instance_id(self) -> str:
        return self._get_callback_instance_name()

    def _get_callback_model_id(self) -> str:
        return str(
            self.params.get("target_model_id")
            or self.params.get("model_id")
            or "host"
        )

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
        logger.info(f"{'=' * 30}")
        logger.info(
            f"🎯 Starting collection V2: model={self.model_id} Plugin: {self.plugin_name}"
        )
        if self.host:
            logger.info(f"📍 Host: {self.host}")
        else:
            logger.info(f"📍 No host specified (cloud collection or default endpoint)")

        try:
            # 根据参数确定执行器类型（job 或 protocol）
            executor_type = self.params["executor_type"]
            logger.info(f"🔧 Executor type: {executor_type}")

            prefer_enterprise = self._get_bool_param(
                self.params, "prefer_enterprise", True
            )
            strict_enterprise = self._get_bool_param(
                self.params, "strict_enterprise", False
            )

            # 插件来源解析入口：先判断 enterprise 能力是否可用，再按
            # enterprise/plugins/inputs/{model}/plugin.yml -> plugins/inputs/{model}/plugin.yml
            # 的顺序选中最终 plugin.yml；若命中 enterprise 且后续 import 失败，executor 会按 strict_enterprise
            # 决定是直接报错还是回退到同名 oss 插件。
            resolved_executor = self.yaml_reader.get_executor_config_with_resolution(
                self.model_id, executor_type, prefer_enterprise=prefer_enterprise
            )
            executor_config = resolved_executor.executor_config
            plugin_resolution = resolved_executor.plugin_resolution

            logger.info(
                f"Plugin source selected: model_id={self.model_id}, selected_source={plugin_resolution.source}, "
                f"selected_plugin_path={plugin_resolution.plugin_path}, has_fallback={plugin_resolution.has_oss_fallback}"
            )

            # 对于job类型且有host，获取节点信息
            if executor_config.is_job and self.host:
                await self.set_node_info()
                if self._node_info:
                    self.params["node_info"] = self._node_info

            # 执行单次采集
            executor = PluginExecutor(
                self.model_id,
                executor_config,
                self.params,
                plugin_resolution=plugin_resolution,
                fallback_executor_config=resolved_executor.fallback_executor_config,
                strict_enterprise=strict_enterprise,
            )
            result = await executor.execute()

            if self.params.get("callback_subject"):
                logger.info("✅ Collection completed successfully (callback mode)")
                logger.info("=" * 60)
                return (
                    result.get("result", {})
                    if result.get("success")
                    else (
                        {
                            "collect_task_id": self.params.get("collect_task_id"),
                            "instance_id": self._get_callback_instance_id(),
                            "instance_name": self._get_callback_instance_name(),
                            "model_id": self._get_callback_model_id(),
                            "file_path": self.params.get("config_file_path", ""),
                            "file_name": self._extract_file_name(self.params.get("config_file_path", "")),
                            "version": "",
                            "status": "error",
                            "size": 0,
                            "error": result.get("result", {}).get(
                                "cmdb_collect_error", result.get("error", "Unknown error")
                            ),
                            "content_base64": "",
                        }
                        if self._is_config_file_callback()
                        else {
                            "collect_task_id": self.params.get("collect_task_id"),
                            "instance_id": self.params.get("instance_id") or self.host or "",
                            "model_id": self.params.get("target_model_id") or self.params.get("model_id"),
                            "file_path": self.params.get("config_file_path", ""),
                            "file_name": self._extract_file_name(self.params.get("config_file_path", "")),
                            "version": "",
                            "status": "error",
                            "size": 0,
                            "error": result.get("result", {}).get(
                                "cmdb_collect_error", result.get("error", "Unknown error")
                            ),
                            "content_base64": "",
                        }
                    )
                )

            # 处理结果并转换为 Prometheus 格式
            processed_data = self._process_result(result)
            final_result = convert_to_prometheus_format(processed_data)

            logger.info(f"✅ Collection completed successfully")
            logger.info("=" * 60)
            return final_result

        except FileNotFoundError as e:
            logger.error(f"❌ YAML config not found: {e}")
            logger.info(f"{'=' * 60}")
            return self._generate_error_response(
                f"Plugin config not found for model '{self.model_id}'"
            )

        except Exception as e:
            logger.error(f"❌ Collection failed: {traceback.format_exc()}")
            logger.info(f"{'=' * 60}")
            return self._generate_error_response(str(e))

    def _process_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单次采集结果

        为采集结果添加必要的元数据字段（host、collect_status等）
        """
        processed = {}

        # 处理采集失败的情况
        if not result.get("success", True):
            logger.warning(
                f"⚠️  Collection failed for {self.host or 'default endpoint'}"
            )

            # 提取错误信息
            result_data = result.get("result", {})
            error_msg = result_data.get(
                "cmdb_collect_error", result.get("error", "Unknown error")
            )

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
                    {"bk_obj_id": model_id, "collect_status": "success"}
                )
                continue

            # 为每个item添加状态和host标签
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        if self.host:
                            item["host"] = self.host
                        item["bk_obj_id"] = model_id
                        item["collect_status"] = "success"
                processed[model_id].extend(items)
            elif isinstance(items, dict):
                # 单个字典的情况
                if self.host:
                    items["host"] = self.host
                items["collect_status"] = "success"
                items["bk_obj_id"] = model_id
                processed[model_id].append(items)

        return processed

    def _generate_error_response(self, error_message: str):
        return self._generate_error_metrics(Exception(error_message), self.model_id)

    def _generate_error_metrics(self, error: Exception, model: str) -> str:
        """生成错误指标（Prometheus 格式）"""
        current_timestamp = int(time.time() * 1000)
        error_type = type(error).__name__
        error_message = str(error).replace('"', '\\"')  # 转义双引号
        plugin_label = f'plugin="{self.plugin_name}",' if self.plugin_name else ""
        prometheus_lines = [
            "# HELP collection_status Collection status indicator",
            "# TYPE collection_status gauge",
            f'collection_status{{{plugin_label}model="{model}",status="error",error_type="{error_type}"}} 1 {current_timestamp}',
            "",
            "# HELP collection_error Collection error details",
            "# TYPE collection_error gauge",
            f'collection_error{{{plugin_label}model="{model}",message="{error_message}"}} 1 {current_timestamp}',
        ]

        return "\n".join(prometheus_lines) + "\n"

    def list_regions(self):
        """
        列出区域（保留向后兼容接口）

        注意：此方法主要用于云平台插件
        """
        if not self.model_id:
            return {"result": [], "success": False, "message": "model_id is required"}

        try:
            resolved_executor = self.yaml_reader.get_executor_config_with_resolution(
                self.model_id, "protocol"
            )
            executor_config = resolved_executor.executor_config

            # 只有 protocol 类型支持 list_regions
            if not executor_config.is_cloud_protocol:
                logger.warning(
                    f"list_regions not supported for executor type: {executor_config.executor_type}"
                )
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

            logger.error(
                f"Error list_regions for {self.plugin_name or self.model_id}: {traceback.format_exc()}"
            )
            return {"result": [], "success": False, "message": str(e)}

    async def set_node_info(self):
        """查询单个节点信息"""
        if not self.connect_ip:
            return

        try:
            exec_params = {"args": [{"page_size": -1}], "kwargs": {}}
            subject = f"{self.namespace}.node_list"
            payload = json.dumps(exec_params).encode()

            response = await nats_request(subject, payload=payload, timeout=10.0)

            if response.get("success") and response["result"]["nodes"]:
                for node in response["result"]["nodes"]:
                    if node["ip"] == self.connect_ip:
                        self._node_info = node
                        logger.info(f"✅ Found node info for {self.connect_ip}")
                        break
                else:
                    logger.warning(f"⚠️  Node info not found for {self.connect_ip}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to get node info for {self.connect_ip}: {e}")
