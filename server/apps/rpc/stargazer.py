import asyncio
import os
from typing import Optional

from apps.rpc.base import RpcClient


class StargazerRpcClient(RpcClient):
    def __init__(self, namespace):
        self.namespace = namespace


class Stargazer(object):
    def __init__(self, instance_id: Optional[str] = None):
        self.instance_id = instance_id or "stargazer"
        self.client = RpcClient(namespace=self.instance_id)
        self.health_check_client = StargazerRpcClient(self.instance_id)

    def list_regions(self, params):
        return_data = self.client.request("list_regions", **params)
        return return_data

    def health_check(self, timeout: int = 5):
        request_data = {"execute_timeout": timeout}
        return_data = self.health_check_client.run("health_check", request_data, _timeout=timeout)
        return return_data

    def collection_tool_debug(self, payload: dict, timeout: int) -> dict:
        """
        通过 NATS request 调用 Stargazer 协议诊断 handler。
        handler 按 protocol 区分：debug_snmp / debug_ipmi。
        nats_timeout = timeout + 5s（缓冲）
        """
        protocol = payload.get("protocol", "snmp")
        handler = f"debug_{protocol}"
        nats_timeout = timeout + 5
        return_data = self.client.request(handler, _timeout=nats_timeout, **payload)
        return return_data

    def dispatch_ip_discovery(self, subnet_ids: list, scan_method: str = "icmp", ports=None) -> None:
        """fire-and-forget：向 Stargazer 下发 IP 探测任务，结果由 Stargazer 异步回推。

        Stargazer 收到消息后执行扫描，完成后将结果 publish 到 payload["callback_subject"]
        （即 "receive_ip_discovery_result"），由本端 NATS listener 接收并调用
        apps.cmdb.nats.nats.receive_ip_discovery_result 落库。

        此处使用 publish（单向，不等待回复），而非 request（需 Stargazer 立即响应），
        因为 IP 扫描是异步长任务。

        TODO(2.7): 确认 Stargazer ip_scan handler 已注册，subject 格式为
        "<stargazer_namespace>.ip_scan"；若 namespace 因接入点不同而变化，
        需从 access_point["id"] 推导 instance_id（参考 CollectModels.access_point 结构）。
        参考文件：agents/stargazer（暂无 ip_scan handler 实现）。
        """
        from apps.cmdb.services.ipam_discovery import build_scan_payload
        import nats_client as nc_module

        payload = build_scan_payload(subnet_ids=subnet_ids, scan_method=scan_method, ports=ports)
        namespace = self.instance_id  # e.g. "stargazer"
        # TODO(2.7): 确认 Stargazer 侧 ip_scan handler 名称（当前假设为 ip_scan）
        asyncio.run(nc_module.publish(namespace, "ip_scan", **payload))
