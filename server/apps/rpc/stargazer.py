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
        """fire-and-forget：向 Stargazer 按子网逐一下发 IP 探测任务，结果由 Stargazer 异步回推。

        每个子网独立下发一条消息（而非合并），payload 携带 subnet_id，
        Stargazer 回调时原样回传，使 receive_ip_discovery_result 能路由到正确的子网台账。

        Stargazer 收到消息后执行扫描，完成后将结果 publish 到 payload["callback_subject"]
        （即 "receive_ip_discovery_result"），由本端 NATS listener 接收并调用
        apps.cmdb.nats.nats.receive_ip_discovery_result 落库。

        此处使用 publish（单向，不等待回复），而非 request（需 Stargazer 立即响应），
        因为 IP 扫描是异步长任务。

        TODO(2.7): 若 namespace 因接入点不同而变化，
        需从 access_point["id"] 推导 instance_id（参考 CollectModels.access_point 结构）。
        当前固定使用 self.instance_id（默认 "stargazer"）。
        subject 格式："{namespace}.ip_scan"，与 agents/stargazer/service/nats_server.py
        中 @register_handler("ip_scan") 注册的 subject 对应。
        """
        from apps.cmdb.services.ipam_discovery import build_scan_payload
        import nats_client as nc_module

        namespace = self.instance_id  # e.g. "stargazer"
        subject = f"{namespace}.ip_scan"

        async def _dispatch_all():
            for subnet_id in subnet_ids:
                payload = build_scan_payload(subnet_id=subnet_id, scan_method=scan_method, ports=ports)
                # publish_raw(subject, dict) sends a flat JSON to the exact subject
                # without the namespace+method_name RPC wrapping used by publish().
                # Resolved: use publish_raw (not publish) for fire-and-forget raw payloads.
                await nc_module.publish_raw(subject, payload)

        asyncio.run(_dispatch_all())
