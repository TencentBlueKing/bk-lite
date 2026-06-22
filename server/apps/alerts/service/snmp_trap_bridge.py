import hashlib
import json
import os
from typing import Any, Dict, Optional

import requests

from apps.alerts.constants.constants import EventAction
from apps.alerts.models.alert_source import AlertSource
from apps.core.logger import alert_logger as logger

# 未命中规则时走保守兜底：只产生事件，不尝试自动恢复，避免误关单。
DEFAULT_UNKNOWN_RULE = {
    "normalized_key": "unknown_trap",
    "item": "snmp_trap:unknown_trap",
    "action": EventAction.CREATED,
    "level": "2",
    "resource_type": "network_device",
}

RULES = {
    "linkdown": {
        "normalized_key": "link_down",
        "item": "snmp_trap:link_down",
        "action": EventAction.CREATED,
        "level": "2",
        "resource_type": "network_device",
    },
    "linkup": {
        "normalized_key": "link_down",
        "item": "snmp_trap:link_down",
        "action": EventAction.RECOVERY,
        "level": "2",
        "resource_type": "network_device",
    },
    "bgp_peer_down": {
        "normalized_key": "bgp_peer_down",
        "item": "snmp_trap:bgp_peer_down",
        "action": EventAction.CREATED,
        "level": "1",
        "resource_type": "network_device",
    },
    "bgp_peer_up": {
        "normalized_key": "bgp_peer_down",
        "item": "snmp_trap:bgp_peer_down",
        "action": EventAction.RECOVERY,
        "level": "1",
        "resource_type": "network_device",
    },
}


def load_bridge_config() -> Dict[str, Any]:
    """读取 bridge 运行配置。

    这里故意把 NATS subject、alerts webhook、重试参数都放在环境变量里，
    这样 bridge 可以独立于日志模块部署，也便于在不同环境中单独调优。
    """
    secret = os.getenv("SNMP_TRAP_ALERTS_SECRET")
    if not secret:
        source = AlertSource.objects.filter(source_id="snmp_trap").only("secret").first()
        secret = source.secret if source else ""

    return {
        "webhook_url": os.getenv(
            "SNMP_TRAP_ALERTS_WEBHOOK_URL",
            "http://127.0.0.1:8000/api/v1/alerts/api/source/snmp_trap/webhook/",
        ),
        "secret": secret,
        "timeout": int(os.getenv("SNMP_TRAP_ALERTS_TIMEOUT", "10")),
        "max_retries": int(os.getenv("SNMP_TRAP_ALERTS_MAX_RETRIES", "3")),
        "subject": os.getenv("SNMP_TRAP_NATS_SUBJECT", "vector"),
        "push_source_id": os.getenv("SNMP_TRAP_PUSH_SOURCE_ID", "snmp_trap_bridge"),
    }


def is_snmp_trap_message(payload: Dict[str, Any]) -> bool:
    """只处理 SNMP Trap 相关消息，避免误消费 vector 上的其它日志事件。"""
    return payload.get("collect_type") == "snmp_trap" or payload.get("event_type") == "snmp_trap"


def extract_base_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """抽取 bridge 后续处理所需的最小公共上下文。"""
    return {
        "trap_message": payload.get("trap_message", "") or "",
        "timestamp": payload.get("timestamp"),
        "received_at": payload.get("received_at"),
        "node_ip": payload.get("node_ip"),
        "collector": payload.get("collector"),
        "raw_payload": payload,
    }


def parse_trap_message(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """从 trap 文本中提取最基础的结构化信息。

    首期只做轻量解析：
    - 识别 trap_oid
    - 命中少量确定性 trap 家族
    - 提取接口等实例键

    更复杂的厂商/MIB 语义可以后续再演进，这里优先保证 bridge 稳定可用。
    """
    msg = (ctx.get("trap_message") or "").lower()

    parsed = {
        "trap_oid": _extract_trap_oid(ctx.get("trap_message", "")),
        "normalized_key": None,
        "instance_key": None,
        "resource_hint": ctx.get("node_ip"),
        "vendor": None,
        "varbinds": _extract_varbinds(ctx.get("trap_message", "")),
    }

    if "linkdown" in msg:
        parsed["normalized_key"] = "linkdown"
    elif "linkup" in msg:
        parsed["normalized_key"] = "linkup"
    elif "bgp" in msg and "down" in msg:
        parsed["normalized_key"] = "bgp_peer_down"
    elif "bgp" in msg and "up" in msg:
        parsed["normalized_key"] = "bgp_peer_up"

    if "ifname" in parsed["varbinds"]:
        parsed["instance_key"] = str(parsed["varbinds"]["ifname"])
    elif "ifindex" in parsed["varbinds"]:
        parsed["instance_key"] = f"ifIndex={parsed['varbinds']['ifindex']}"

    return parsed


def resolve_rule(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """把解析结果映射到统一的告警规则。

    这里返回的是“告警家族语义”，而不是原始 trap 语义：
    例如 linkDown / linkUp 最终都归到 link_down 这条告警链上，
    只是在 action 上分别体现为 created / recovery。
    """
    normalized_key = parsed.get("normalized_key")
    if not normalized_key:
        return DEFAULT_UNKNOWN_RULE
    return RULES.get(str(normalized_key), DEFAULT_UNKNOWN_RULE)


def resolve_resource_identity(ctx: Dict[str, Any], parsed: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, Any]:
    """生成资源身份。

    首期优先保证“有稳定 resource_id”，资源模型不做过度推断；
    缺少更细粒度资源时退化到 node_ip。
    """
    resource_id = parsed.get("resource_hint") or ctx.get("node_ip") or "unknown"
    return {
        "resource_id": resource_id,
        "resource_name": resource_id,
        "resource_type": rule["resource_type"],
    }


def build_external_id(rule: Dict[str, Any], resource: Dict[str, Any], parsed: Dict[str, Any]) -> str:
    """生成稳定的事件外部身份。

    这里故意不直接把 trap_oid 放进指纹。
    否则像 linkDown/linkUp 这种一对 created/recovery trap 会因为 OID 不同
    被算成两条不同身份链，恢复事件就无法关联回原始告警。
    """
    fingerprint = {
        "normalized_key": rule["normalized_key"],
        "resource_id": resource.get("resource_id") or "unknown",
        "instance_key": parsed.get("instance_key") or "default",
    }
    raw = json.dumps(fingerprint, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_event(payload: Dict[str, Any], push_source_id: str = "snmp_trap_bridge") -> Optional[Dict[str, Any]]:
    """把 vector/NATS 消息转换成 alerts 能直接消费的标准 event。"""
    if not is_snmp_trap_message(payload):
        return None

    ctx = extract_base_context(payload)
    parsed = parse_trap_message(ctx)
    rule = resolve_rule(parsed)
    resource = resolve_resource_identity(ctx, parsed, rule)
    external_id = build_external_id(rule, resource, parsed)
    start_time = ctx.get("timestamp") or ctx.get("received_at")

    return {
        "push_source_id": push_source_id,
        "title": _build_title(rule, resource, parsed),
        "description": ctx.get("trap_message") or "SNMP trap received",
        "item": rule["item"],
        "level": rule["level"],
        "action": rule["action"],
        "start_time": str(start_time) if start_time else None,
        "external_id": external_id,
        "resource_id": resource["resource_id"],
        "resource_name": resource["resource_name"],
        "resource_type": resource["resource_type"],
        "labels": {
            "collect_type": payload.get("collect_type"),
            "event_type": payload.get("event_type"),
            "collector": ctx.get("collector"),
            "node_ip": ctx.get("node_ip"),
            "normalized_key": rule["normalized_key"],
            "trap_oid": parsed.get("trap_oid"),
            "varbinds": parsed.get("varbinds", {}),
            "raw_message": ctx.get("trap_message"),
            "raw_payload": ctx.get("raw_payload"),
        },
    }


def build_webhook_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """复用 alerts 现有 source webhook 入口要求的 `events` 包装格式。"""
    return {"events": [event]}


def send_to_alerts(webhook_payload: Dict[str, Any], config: Dict[str, Any]) -> None:
    """把标准事件投递到告警中心。

    这里实现的是最小可用重试：
    - bridge 不负责持久化失败消息
    - 但会做有限次重试并打印日志，方便定位投递失败
    """
    last_error: Optional[Exception] = None
    retries = max(config.get("max_retries", 1), 1)
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                config["webhook_url"],
                headers={
                    "SECRET": config["secret"],
                    "Content-Type": "application/json",
                },
                json=webhook_payload,
                timeout=config.get("timeout", 10),
            )
            response.raise_for_status()
            return
        except requests.RequestException as err:
            last_error = err
            logger.warning(
                "snmp trap bridge delivery failed, attempt=%s, url=%s, error=%s",
                attempt,
                config.get("webhook_url"),
                str(err),
            )
    if last_error is not None:
        raise last_error
    raise RuntimeError("snmp trap bridge delivery failed without exception details")


def handle_vector_message(payload: Dict[str, Any], config: Dict[str, Any]) -> bool:
    """bridge 单条消息入口。

    返回值用于区分：
    - False：非 SNMP Trap，或被主动忽略
    - True：已识别并尝试投递
    """
    event = build_event(payload, push_source_id=config.get("push_source_id", "snmp_trap_bridge"))
    if not event:
        return False
    webhook_payload = build_webhook_payload(event)
    send_to_alerts(webhook_payload, config)
    return True


def _extract_trap_oid(message: str) -> Optional[str]:
    """优先从 snmpTrapOID.0 varbind 里取 trap_oid，再退化到简单 token 扫描。"""
    if not message:
        return None
    varbinds = _extract_varbinds(message)
    trap_oid = varbinds.get("snmptrapoid.0")
    if trap_oid:
        return trap_oid
    if "1.3.6.1" in message:
        for token in message.replace(",", " ").split():
            if token.startswith("1.3.6.1"):
                return token.strip()
    return None


def _extract_varbinds(message: str) -> Dict[str, str]:
    """从原始 trap 文本中做轻量 varbind 提取。

    这里不追求完整协议级解析，只提取 `key=value` 结构用于归一化和排障。
    """
    if not message:
        return {}
    result = {}
    for token in message.replace(",", " ").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.split("::")[-1].strip().strip(":").lower()
        if not key:
            continue
        result[key] = value.strip()
    return result


def _build_title(rule: Dict[str, Any], resource: Dict[str, Any], parsed: Dict[str, Any]) -> str:
    """生成可读标题，优先体现告警家族、资源和实例键。"""
    resource_name = resource.get("resource_name") or resource.get("resource_id") or "unknown"
    instance_key = parsed.get("instance_key")
    if instance_key:
        return f"SNMP Trap {rule['normalized_key']} on {resource_name} ({instance_key})"
    return f"SNMP Trap {rule['normalized_key']} on {resource_name}"
