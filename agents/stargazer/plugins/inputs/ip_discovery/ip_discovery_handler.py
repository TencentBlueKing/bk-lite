# -- coding: utf-8 --
"""IP 发现 NATS handler：接收 server 下发的扫描任务，执行扫描，回推结果。规格 §13。

本模块只包含纯业务逻辑函数（无 @register_handler 装饰器），便于单元测试。
handler 的 NATS subject 注册由调用方（service/nats_server.py）完成：
    from core.nats import register_handler
    from plugins.inputs.ip_discovery.ip_discovery_handler import handle_ip_scan
    register_handler("ip_scan")(handle_ip_scan)

Subject：{stargazer_namespace}.ip_scan（与 server dispatch_ip_discovery 下发的 subject 对应）。

回调格式（publish 到 {NATS_NAMESPACE}.{callback_subject}）：
    {"args": [], "kwargs": {"data": {"subnet_id": ..., "alive": [{...}, ...]}}}
    server 端 @nats_client.register receive_ip_discovery_result(data) 按此约定解包。

TODO(2.7): 确认 NATS_NAMESPACE 环境变量在生产环境与 server 端一致（当前默认 "bklite"）。
TODO(2.7): 若 callback_subject 不在 payload 中（异常情况），结果将无法回推 server，仅记录日志。
"""
import os
import traceback

from sanic.log import logger

from core.nats_utils import nats_publish
from plugins.inputs.ip_discovery.ip_discovery_scanner import IPDiscoveryScanner


async def _publish_ip_discovery_result(callback_subject: str, result_data: dict) -> None:
    """将扫描结果按 server NATS 约定格式推送回 server。

    server 端 @nats_client.register 函数按 {"args": [], "kwargs": {"data": ...}} 解包参数。

    TODO(2.7): 确认 NATS_NAMESPACE 与 server 端一致；若 server 用不同 namespace，需对齐。
    """
    nats_namespace = os.getenv("NATS_NAMESPACE", "bklite")
    subject = f"{nats_namespace}.{callback_subject}"
    payload = {"args": [], "kwargs": {"data": result_data}}
    await nats_publish(subject, payload)
    logger.info(
        "[IPDiscovery] Published result to %s subnet_id=%s alive_count=%s",
        subject,
        result_data.get("subnet_id"),
        len(result_data.get("alive", [])),
    )


async def handle_ip_scan(data: dict) -> dict:
    """接收 server 下发的单子网 IP 扫描任务，执行扫描后将存活 IP 回推 server。

    预期入参（由 server dispatch_ip_discovery build_scan_payload 构造）：
        {
            "model_id": "ip",
            "subnet_id": <int|str>,         # 子网 _id，原样回传给 server
            "scan_method": "icmp"|"tcp",
            "ports": [...],
            "targets": ["10.0.1.2", ...],   # 已排除网络/广播/网关
            "callback_subject": "receive_ip_discovery_result"
        }

    返回（同时 publish 到 callback_subject）：
        {"subnet_id": ..., "alive": [{"ip": ..., "mac": ...}, ...]}

    TODO(2.7): 若 data 中缺少 subnet_id（旧版 server），alive 列表将仍被推送
    但 server 端会因 subnet_id missing 而丢弃；需保持 server/agent 协议版本一致。
    """
    subnet_id = data.get("subnet_id")
    callback_subject = data.get("callback_subject", "receive_ip_discovery_result")

    logger.info(
        "[IPDiscovery] Received ip_scan task subnet_id=%s targets_count=%s scan_method=%s",
        subnet_id,
        len(data.get("targets") or []),
        data.get("scan_method", "icmp"),
    )

    try:
        scanner = IPDiscoveryScanner(data)
        raw = await scanner.list_all_resources()
        # list_all_resources 返回 {"success": True, "result": {"ip": [{"ip", "mac"}, ...]}}
        alive = (raw.get("result") or {}).get("ip") or []
    except Exception as exc:
        logger.error(
            "[IPDiscovery] Scanner error subnet_id=%s: %s\n%s",
            subnet_id,
            exc,
            traceback.format_exc(),
        )
        alive = []

    result_data = {"subnet_id": subnet_id, "alive": alive}

    try:
        await _publish_ip_discovery_result(callback_subject, result_data)
    except Exception as exc:
        logger.error(
            "[IPDiscovery] Failed to publish result subnet_id=%s: %s\n%s",
            subnet_id,
            exc,
            traceback.format_exc(),
        )

    return result_data
