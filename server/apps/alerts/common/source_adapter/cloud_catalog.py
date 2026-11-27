# -- coding: utf-8 --
"""阿里云 EventBridge 与腾讯云事件总线的上报目录。

目录随代码发布。解析只认这里的事件名，不读库里可编辑的映射。
"""

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

ALIYUN_CATALOG = {
    "InstanceFailure.Reboot": {"title": "因实例错误实例重启", "level": "0", "kind": "instance", "stateless": False},
    "SystemFailure.Reboot": {"title": "因系统错误实例重启", "level": "0", "kind": "instance", "stateless": False},
    "SystemFailure.Stop": {"title": "因系统错误实例停止", "level": "0", "kind": "instance", "stateless": False},
    "SystemFailure.Redeploy": {"title": "因系统错误实例重新部署", "level": "0", "kind": "instance", "stateless": False},
    "SystemFailure.Delete": {"title": "因创建失败实例自动释放", "level": "0", "kind": "instance", "stateless": False},
    "SystemMaintenance.Reboot": {"title": "因系统维护实例计划重启", "level": "2", "kind": "instance", "stateless": False},
    "SystemMaintenance.Stop": {"title": "因系统维护实例计划停止", "level": "2", "kind": "instance", "stateless": False},
    "SystemMaintenance.Redeploy": {"title": "因系统维护实例计划重新部署", "level": "2", "kind": "instance", "stateless": False},
    "SystemMaintenance.IsolateErrorDisk": {"title": "因系统维护隔离坏盘", "level": "2", "kind": "instance", "stateless": False},
    "SystemMaintenance.ReInitErrorDisk": {"title": "因系统维护重新初始化坏盘", "level": "2", "kind": "instance", "stateless": False},
    "SystemMaintenance.RebootAndIsolateErrorDisk": {"title": "因系统维护重启实例并隔离坏盘", "level": "2", "kind": "instance", "stateless": False},
    "SystemMaintenance.RebootAndReInitErrorDisk": {"title": "因系统维护重启实例并重新初始化坏盘", "level": "2", "kind": "instance", "stateless": False},
    "ErrorDetected": {"title": "本地磁盘出现损坏告警", "level": "0", "kind": "disk", "stateless": False},
    "Stalled": {"title": "磁盘性能受到严重影响", "level": "0", "kind": "disk", "stateless": False},
    "StateChange": {"title": "实例生命周期状态变化", "level": "3", "kind": "instance", "stateless": True},
    "PreemptibleInstanceInterruption": {"title": "抢占式实例被释放", "level": "3", "kind": "instance", "stateless": True},
    "LiveMigrationAcrossDDH": {"title": "专有宿主机上的 ECS实例热迁移", "level": "3", "kind": "instance", "stateless": True},
    "OverduePaymentRelease": {"title": "块存储欠费释放", "level": "3", "kind": "disk", "stateless": True},
}

TENCENT_TITLES = {
    "guest_reboot": "客户机重启",
}

_FIRING = {"Executing"}
_RECOVERY = {"Executed", "Avoided", "Canceled"}
_FAILED = {"Failed"}
_STATELESS_PHASE = {"Scheduled", "Inquiring"}
_TENCENT_FIRING = {"1", "未恢复"}
_TENCENT_RECOVERY = {"0", "恢复"}
_FAILURE_TOKENS = ("reboot", "failure", "crash", "panic", "hang")
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def catalog_rows(vendor):
    """接入说明用的只读目录行。"""
    if vendor == "aliyun":
        return [
            {
                "event": key,
                "title": row["title"],
                "level": row["level"],
                "resource": row["kind"],
                "stateless": row["stateless"],
            }
            for key, row in ALIYUN_CATALOG.items()
        ]
    return [
        {"event": "guest_reboot", "title": "客户机重启", "level": "0", "resource": "cvm", "stateless": False},
        {"event": "其他 CVM 事件", "title": "事件名本身", "level": "2", "resource": "cvm", "stateless": False},
    ]


def catalog_text(vendor):
    """写进集成源字段说明，详情页现有的说明区能直接展示。"""
    if vendor == "aliyun":
        lines = [
            "上报字段映射随版本发布。账号 aliyunaccountid，地域 aliyunregionid，业务 ID data.eventId。",
            "实例资源 ID 取 data.instanceId 或 data.resourceId。磁盘资源 ID 取 data.diskId，关联 CMDB 用 data.ecsInstanceId。",
            "Executing 发生；Executed、Avoided、Canceled 恢复；Failed 发生但不新开告警；Scheduled、Inquiring 和无状态原生事件记为无状态。",
        ]
        for key, row in ALIYUN_CATALOG.items():
            lines.append(f"{key} | {row['title']} | 级别 {row['level']} | {row['kind']}")
        return "\n".join(lines)
    lines = [
        "只收 CVM。监控模板资源 ID 是 dimensions.unInstanceId，业务 ID 是 sessionId，状态是 alarmStatus，时间 firstOccurTime 按东八区。",
        "CloudEvent 资源 ID 是 subject，账号是 appId，时间 time 为毫秒。状态 1 或未恢复为发生，0 或恢复为恢复，其它为无状态。",
        "不能加请求头时，把同一枚组织密钥放在查询参数 secret。其它云产品跳过。对不上监控模板或 CloudEvent 的包会拒绝。",
        "guest_reboot | 客户机重启 | 级别 0 | cvm",
        "其余 CVM 事件 | 事件名 | 级别 2 | cvm",
    ]
    return "\n".join(lines)


def to_epoch_ms(value):
    """把厂商时间收成毫秒字符串。无法识别时返回 None，交给现有映射补接收时间。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and str(value).strip().lstrip("-").isdigit()):
        digits = str(int(value))
        if len(digits) in (10, 13):
            return digits
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_SHANGHAI)
    return str(int(parsed.timestamp() * 1000))


def _clip(value, limit):
    return str(value or "")[:limit]


def _description(account, region, word, failed=False, extra=""):
    parts = [part for part in (account, region, word) if part]
    if failed:
        parts.append("失败")
    if extra:
        parts.append(extra)
    return "，".join(parts)


def _event_shell(
    body,
    account,
    region,
    resource_id,
    resource_name,
    resource_type,
    item,
    title,
    level,
    action,
    word,
    business,
    failed=False,
    extra="",
    rule_id="",
):
    start = to_epoch_ms(body.get("_parsed_time"))
    event = {
        "title": _clip(f"{title} {resource_id}".strip(), 200),
        "description": _description(account, region, word, failed=failed, extra=extra),
        "level": level,
        "item": _clip(item, 128),
        "external_id": _clip(f"{account}:{business}", 128),
        "resource_id": _clip(resource_id, 100),
        "resource_type": _clip(resource_type, 100),
        "action": action,
        "original": deepcopy(body.get("_original", body)),
    }
    if start:
        event["start_time"] = start
    if resource_name:
        event["resource_name"] = _clip(resource_name, 128)
    if region:
        event["location"] = _clip(region, 200)
    if account:
        event["labels"] = {"account": _clip(account, 128)}
    if rule_id:
        event["rule_id"] = _clip(rule_id, 100)
    return event


def _aliyun_identity(event_type):
    if "[" in event_type and "]" in event_type:
        inner = event_type.split("[", 1)[1].split("]", 1)[0]
        name, phase = inner.rsplit(":", 1) if ":" in inner else (inner, "")
        head = event_type.split("[", 1)[0]
        return name, phase, head
    parts = event_type.split(":")
    return (parts[-1] if parts else ""), "", event_type


def _aliyun_kind(head, catalog_kind):
    if head.endswith("Disk") or ":Disk" in head:
        return "disk"
    if head.endswith("Instance") or ":Instance" in head:
        return "instance"
    return catalog_kind


def _is_aliyun(body):
    source = str(body.get("source") or "")
    event_type = str(body.get("type") or "")
    return bool(body.get("aliyunaccountid")) or source.startswith("acs.") or event_type.startswith("ecs:")


def parse_aliyun(body):
    """返回 accept / skip / reject，以及可映射的标准事件。"""
    if not isinstance(body, dict) or not _is_aliyun(body):
        return {"outcome": "reject", "event_type": "", "event": None}
    event_type = str(body.get("type") or "")
    name, phase, head = _aliyun_identity(event_type)
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    if not phase:
        phase = str(data.get("eventStatus") or "")
    entry = ALIYUN_CATALOG.get(name)
    if entry is None:
        return {"outcome": "skip", "event_type": event_type or name, "event": None}
    kind = _aliyun_kind(head, entry["kind"])
    if kind == "disk":
        resource_id = data.get("diskId") or data.get("resourceId") or ""
        resource_name = data.get("diskName") or ""
        resource_type = "aliyun_disk"
        cmdb_resource = data.get("ecsInstanceId") or data.get("instanceId") or ""
    else:
        resource_id = data.get("instanceId") or data.get("resourceId") or ""
        resource_name = data.get("instanceName") or data.get("ecsInstanceName") or ""
        resource_type = "aliyun_ecs"
        cmdb_resource = resource_id
    account = str(body.get("aliyunaccountid") or "")
    region = str(body.get("aliyunregionid") or "")
    business = str(data.get("eventId") or "") or f"{resource_id}:{name}"
    if entry["stateless"]:
        action, word, level, failed, extra = "record", "无状态", "3", False, ""
    elif phase in _FIRING:
        action, word, level, failed, extra = "created", "发生", entry["level"], False, ""
    elif phase in _RECOVERY:
        action, word, level, failed, extra = "recovery", "恢复", entry["level"], False, ""
    elif phase in _FAILED:
        action, word, level, failed, extra = "created", "发生", entry["level"], True, ""
    elif phase in _STATELESS_PHASE:
        action, word, level, failed, extra = "record", "无状态", "3", False, ""
    else:
        action, word, level, failed, extra = "record", "无状态", "3", False, phase
    stamped = dict(body)
    stamped["_parsed_time"] = body.get("time")
    stamped["_original"] = body
    event = _event_shell(
        stamped,
        account,
        region,
        str(resource_id),
        str(resource_name),
        resource_type,
        name,
        entry["title"],
        level,
        action,
        word,
        business,
        failed=failed,
        extra=extra,
    )
    return {
        "outcome": "accept",
        "event_type": event_type or name,
        "event": event,
        "cmdb_model": "aliyun_ecs",
        "cmdb_resource_id": str(cmdb_resource or ""),
    }


def _tencent_shape(body):
    if str(body.get("alarmType") or body.get("alarmtype") or "") == "event":
        return "alarm"
    if body.get("specversion") and body.get("type"):
        return "cloudevent"
    return ""


def _is_cvm_type(event_type):
    parts = [part.lower() for part in str(event_type or "").split(":") if part]
    return "cvm" in parts


def _tencent_level(event_name, action):
    if action == "record":
        return "3"
    name = str(event_name or "").lower()
    if any(token in name for token in _FAILURE_TOKENS):
        return "0"
    return "2"


def _first_text(sources, keys):
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return str(value)
    return ""


def _tencent_status(status):
    text = str(status).strip() if status is not None else ""
    if text in _TENCENT_FIRING:
        return "created", "发生", ""
    if text in _TENCENT_RECOVERY:
        return "recovery", "恢复", ""
    extra = "" if text in {"", "无状态"} else text
    return "record", "无状态", extra


def parse_tencent(body):
    if not isinstance(body, dict):
        return {"outcome": "reject", "event_type": "", "event": None}
    shape = _tencent_shape(body)
    if not shape:
        return {"outcome": "reject", "event_type": "", "event": None}
    if shape == "alarm":
        policy = body.get("alarmPolicyInfo") if isinstance(body.get("alarmPolicyInfo"), dict) else {}
        conditions = policy.get("conditions") if isinstance(policy.get("conditions"), dict) else {}
        product = str(conditions.get("productName") or "")
        event_name = str(conditions.get("eventName") or "")
        event_type = event_name or product or "event"
        if product.lower() != "cvm":
            return {"outcome": "skip", "event_type": event_type, "event": None}
        obj = body.get("alarmObjInfo") if isinstance(body.get("alarmObjInfo"), dict) else {}
        dimensions = obj.get("dimensions") if isinstance(obj.get("dimensions"), dict) else {}
        resource_id = str(dimensions.get("unInstanceId") or "")
        region = str(obj.get("region") or "")
        account = _first_text((body, obj), ("appId", "ownerUin", "uin"))
        business = str(body.get("sessionId") or "") or f"{resource_id}:{event_name}"
        action, word, extra = _tencent_status(body.get("alarmStatus", body.get("status")))
        when = body.get("firstOccurTime")
        rule_id = str(policy.get("policyName") or "")
    else:
        event_type = str(body.get("type") or "")
        if not _is_cvm_type(event_type):
            return {"outcome": "skip", "event_type": event_type, "event": None}
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        event_name = event_type.split(":")[-1]
        resource_id = str(body.get("subject") or "")
        region = str(body.get("region") or data.get("region") or "")
        account = _first_text((body, data), ("appId", "ownerUin", "uin"))
        business = str(body.get("sessionId") or data.get("sessionId") or "") or f"{resource_id}:{event_name}"
        action, word, extra = _tencent_status(body.get("status", data.get("status")))
        when = body.get("time")
        rule_id = str(body.get("ruleName") or data.get("ruleName") or "")
    title = TENCENT_TITLES.get(event_name, event_name or "CVM 事件")
    stamped = dict(body)
    stamped["_parsed_time"] = when
    stamped["_original"] = body
    event = _event_shell(
        stamped,
        account,
        region,
        resource_id,
        "",
        "qcloud_cvm",
        event_name or event_type,
        title,
        _tencent_level(event_name, action),
        action,
        word,
        business,
        extra=extra,
        rule_id=rule_id,
    )
    return {
        "outcome": "accept",
        "event_type": event_type,
        "event": event,
        "cmdb_model": "qcloud_cvm",
        "cmdb_resource_id": resource_id,
    }


def parse_body(vendor, body):
    if vendor == "aliyun":
        return parse_aliyun(body)
    if vendor == "tencent":
        return parse_tencent(body)
    return {"outcome": "reject", "event_type": "", "event": None}
