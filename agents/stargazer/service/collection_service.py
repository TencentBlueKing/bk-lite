"""采集服务 V2 - 基于 YAML 配置的新版本采集服务"""
import asyncio
import copy
import importlib
import json
import time
import traceback
from typing import Dict, Any, Optional, List
from sanic.log import logger

from core.nats_utils import nats_request
from core.yaml_reader import yaml_reader
from core.plugin_executor import PluginExecutor
from plugins.base_utils import expand_ip_range
from utils.async_executor import AsyncExecutor
from plugins.base_utils import convert_to_prometheus_format


class CollectionService:
    """
    采集服务- 基于 YAML 配置的新架构
    
    工作流程：
    1. 根据 plugin_name 推断 model（或直接传入 model）
    2. 读取 plugins/inputs/{model}/plugin.yml
    3. 确定执行器类型（job/protocol）
    4. 通过 PluginExecutor 执行采集
    """

    def __init__(self, params: Optional[dict] = None, max_workers: Optional[int] = None):
        self._node_info_map = {}
        self.namespace = "bklite"
        self.yaml_reader = yaml_reader
        self.params = params
        self.plugin_name = self.params.pop("plugin_name", None)
        self.model_id = self.params["model_id"]
        self.hosts = self.ip_split(self.params.get("hosts", ""))
        # 是否启用并发（默认启用）
        self.enable_concurrent = len(self.hosts) >= 2
        if self.enable_concurrent:
            # 初始化异步执行器
            self.async_executor = AsyncExecutor(max_workers=max_workers)
        else:
            self.async_executor = None

    @staticmethod
    def ip_split(ip_range):
        if "-" in ip_range:
            result = expand_ip_range(ip_range=ip_range)
        else:
            result = ip_range.split(",")

        return result

    async def collect(self):
        """
        Returns:
            采集结果（Prometheus 格式字符串 或 字典）
        """
        logger.info(f"{'=' * 30}")
        logger.info(f"🎯 Starting collection V2: model={self.model_id} Plugin: {self.plugin_name}")
        if not self.hosts:
            logger.warning("❌ Hosts parameter is empty")

        try:
            # 根据参数确定执行器类型（job 或 protocol）
            executor_type = self.params["executor_type"]
            logger.info(f"🔧 Executor type: {executor_type}")

            #  获取执行器配置
            executor_config = self.yaml_reader.get_executor_config(self.model_id, executor_type)

            # 对于非云协议采集，先获取节点信息
            if executor_config.is_job:
                await self.set_nodes_info_map()

            # 判断是否启用并发
            if self.enable_concurrent:
                logger.info(f"🚀 Concurrent mode enabled for {len(self.hosts)} hosts")
                collect_data = await self._collect_concurrent(executor_config)
            else:
                logger.info(f"📝 Sequential mode for {len(self.hosts)} host(s)")
                collect_data = await self._collect_sequential(executor_config)

            # 合并多主机数据并转换为 Prometheus 格式
            merged_data = self._merge_raw_data(collect_data)
            result = convert_to_prometheus_format(merged_data)

            logger.info(f"✅ Collection completed successfully")
            logger.info('=' * 60)
            return result

        except FileNotFoundError as e:
            logger.error(f"❌ YAML config not found: {e}")
            logger.info(f"{'=' * 60}")
            return self._generate_error_response(f"Plugin config not found for model '{self.model_id}'")

        except Exception as e:
            logger.error(f"❌ Collection failed: {traceback.format_exc()}")
            logger.info(f"{'=' * 60}")
            return self._generate_error_response(str(e))

        finally:
            # 清理线程池资源
            if self.async_executor:
                self.async_executor.shutdown(wait=False)

    async def _collect_single_host(self, host: str, executor_config) -> Dict[str, Any]:
        """采集单个主机的数据"""
        try:
            # 为每个主机创建独立的参数副本
            host_params = copy.deepcopy(self.params)
            host_params["host"] = host

            if executor_config.is_job:
                if host in self._node_info_map:
                    host_params["node_info"] = self._node_info_map[host]

            executor = PluginExecutor(self.model_id, executor_config, host_params)
            return await executor.execute()
        except Exception as e:
            logger.error(f"❌ Host {host} collection failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "host": host
            }

    async def _collect_sequential(self, executor_config) -> List[Dict[str, Any]]:
        """串行采集（原有逻辑）"""
        collect_data = []
        for host in self.hosts:
            result = await self._collect_single_host(host, executor_config)
            collect_data.append(result)
        return collect_data

    async def _collect_concurrent(self, executor_config) -> List[Dict[str, Any]]:
        """并发采集（使用异步任务优化）"""
        # 创建所有主机的采集任务
        tasks = [
            self._collect_single_host(host, executor_config)
            for host in self.hosts
        ]
        # 使用 asyncio.gather 并发执行所有任务
        return await asyncio.gather(*tasks, return_exceptions=False)

    def _merge_raw_data(self, raw_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并多个主机的原始数据"""
        merged = {}
        # 判断是否需要添加 host 字段（云平台采集不需要）
        has_hosts = self.hosts and len(self.hosts) > 0

        for i, data in enumerate(raw_data_list):
            # 只有在有 hosts 的情况下才获取 current_host
            current_host = None
            if has_hosts and i < len(self.hosts):
                current_host = self.hosts[i]

            # 处理采集失败的情况
            if not data.get("success", True):
                error_context = f"Host {current_host}" if current_host else f"Index {i}"
                logger.warning(f"⚠️  {error_context} collection failed")

                # 提取错误信息
                result_data = data.get("result", {})
                error_msg = result_data.get("cmdb_collect_error", data.get("error", "Unknown error"))

                # 创建错误记录，保留到结果中
                error_record = {
                    "collect_status": "failed",
                    "collect_error": error_msg,
                    "bk_obj_id": self.model_id
                }
                # 只有在有 host 的情况下才添加 host 字段
                if current_host:
                    error_record["host"] = current_host

                # 将错误记录添加到对应的模型中
                if self.model_id not in merged:
                    merged[self.model_id] = []
                merged[self.model_id].append(error_record)
                continue

            result_data = data.get("result", {})
            for model_id, items in result_data.items():
                if model_id not in merged:
                    merged[model_id] = []

                if not items:
                    merged[model_id].extend([{"bk_obj_id": model_id, "collect_status": "success"}])
                    continue

                # 为每个 item 添加状态和 host 标签（仅在有 host 时添加）
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            # 只有在有 host 的情况下才添加 host 字段
                            if current_host:
                                item['host'] = current_host
                            item["bk_obj_id"] = model_id
                            item['collect_status'] = 'success'
                    merged[model_id].extend(items)
                elif isinstance(items, dict):
                    # 单个字典的情况
                    if current_host:
                        items['host'] = current_host
                    items['collect_status'] = 'success'
                    merged[model_id].append(items)

        return merged

    def _generate_error_response(self, error_message: str):
        return self._generate_error_metrics(Exception(error_message), self.model_id)

    def _generate_error_metrics(self, error: Exception, model: str) -> str:
        """生成错误指标（Prometheus 格式）"""
        current_timestamp = int(time.time() * 1000)
        error_type = type(error).__name__
        error_message = str(error).replace('"', '\\"')  # 转义双引号
        plugin_label = f'plugin="{self.plugin_name}",' if self.plugin_name else ''
        prometheus_lines = [
            "# HELP collection_status Collection status indicator",
            "# TYPE collection_status gauge",
            f'collection_status{{{plugin_label}model="{model}",status="error",error_type="{error_type}"}} 1 {current_timestamp}',
            "",
            "# HELP collection_error Collection error details",
            "# TYPE collection_error gauge",
            f'collection_error{{{plugin_label}model="{model}",message="{error_message}"}} 1 {current_timestamp}'
        ]

        return "\n".join(prometheus_lines) + "\n"

    def list_regions(self):
        """
        列出区域（保留向后兼容接口）
        
        注意：此方法主要用于云平台插件
        """
        if not self.model_id:
            return {"result": [], "success": False}

        try:
            # 读取 YAML 配置
            plugin_config = self.yaml_reader.read_plugin_config(self.model_id)
            executor_config = self.yaml_reader.get_executor_config(self.model_id,
                                                                   plugin_config.get('default_executor', 'protocol'))

            # 只有 protocol 类型支持 list_regions
            if not executor_config.is_cloud_protocol:
                logger.warning(f"list_regions not supported for executor type: {executor_config.executor_type}")
                return {"result": [], "success": False}

            # 加载采集器
            collector_info = executor_config.get_collector_info()
            module = importlib.import_module(collector_info['module'])
            plugin_class = getattr(module, collector_info['class'])

            # 实例化并调用
            plugin_instance = plugin_class(self.params or {})
            result = plugin_instance.list_regions()

            return {"result": result.get("data", []), "success": result.get("result", False)}

        except Exception as e:  # noqa
            import traceback
            logger.error(f"Error list_regions for {self.plugin_name or self.model_id}: {traceback.format_exc()}")
            return {"result": [], "success": False}

    async def set_nodes_info_map(self):
        """查询节点信息"""
        try:
            exec_params = {
                "args": [{"page_size": -1}],
                "kwargs": {}
            }
            subject = f"{self.namespace}.node_list"
            payload = json.dumps(exec_params).encode()

            response = await nats_request(subject, payload=payload, timeout=10.0)

            if response.get('success') and response['result']['nodes']:
                for node in response['result']['nodes']:
                    self._node_info_map[node["ip"]] = node
        except Exception as e:
            logger.warning(f"⚠️  Failed to get node info: {e}")
