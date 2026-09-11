"""周期错峰插件登记与通道解释；保存和节点渲染共用此入口。"""
from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from apps.cmdb.models.collect_model import normalize_topology_contract


@dataclass(frozen=True)
class OffsetChannel:
    model_id: str
    plugin_name: str
    role: str
    offset_key: str
    cycle_param: str = ""
    enabled_param: str = ""


# 接入新的现有 Telegraf 插件只需登记其模型、角色和字段，并补保存/渲染契约测试。
OFFSET_CHANNELS = (
    OffsetChannel("host", "host_info", "device", "collection_offset_seconds"),
    OffsetChannel("network", "snmp_facts", "device", "collection_offset_seconds"),
    OffsetChannel("network", "snmp_topo", "topology", "topology_collection_offset_seconds", "topology_interval_minutes", "has_network_topo"),
)


def supported_model_ids() -> set[str]:
    return {channel.model_id for channel in OFFSET_CHANNELS}


def supports_task(task) -> bool:
    model_id = task.get("model_id") if isinstance(task, dict) else getattr(task, "model_id", None)
    return model_id in supported_model_ids()


def effective_offset_seconds(value, interval_seconds: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return 0
    try:
        seconds = int(value)
    except ValueError:
        return 0
    return seconds if 0 <= seconds < interval_seconds else 0


def active_channels(task) -> list[tuple[OffsetChannel, int]]:
    if not supports_task(task) or not getattr(task, "is_interval", False) or getattr(task, "cycle_value_type", "") != "cycle":
        return []
    try:
        cycle = int(task.cycle_value)
    except (TypeError, ValueError):
        return []
    if cycle < 1:
        return []
    params = dict(task.params or {})
    if task.model_id == "network":
        params.update(normalize_topology_contract(params, device_cycle_minutes=cycle))
    return [
        (channel, int(params[channel.cycle_param]) if channel.cycle_param else cycle)
        for channel in OFFSET_CHANNELS
        if channel.model_id == task.model_id and (not channel.enabled_param or params.get(channel.enabled_param))
    ]


def rendered_offset_seconds(task, plugin_name: str, interval_seconds: int) -> int | None:
    for channel, _cycle in active_channels(task):
        if channel.plugin_name == plugin_name:
            return effective_offset_seconds((task.params or {}).get(channel.offset_key), interval_seconds)
    return None


def restore_owned_offsets(data: dict, previous=None) -> None:
    """用户提交不能覆盖偏移；缺字段的普通表单编辑也要保留服务端状态。"""
    if not supports_task(data) and (previous is None or not supports_task(previous)):
        return
    old_params = dict(previous.params or {}) if previous is not None else {}
    params = dict(data.get("params", old_params) or {})
    for key in {channel.offset_key for channel in OFFSET_CHANNELS}:
        params.pop(key, None)
        if key in old_params:
            params[key] = old_params[key]
    data["params"] = params


def target_count(task) -> int:
    if task.instances:
        return len(task.instances)
    count = 0
    for token in str(task.ip_range or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            if "/" in token:
                count += ip_network(token, strict=False).num_addresses
            elif "-" in token:
                start, end = (ip_address(part.strip()) for part in token.split("-", 1))
                if start.version != end.version or int(end) < int(start):
                    raise ValueError("invalid address range")
                count += int(end) - int(start) + 1
            else:
                count += 1
        except ValueError:
            # 与采集端一致：不能解释成地址段的主机名/字面目标仍按一个目标计数。
            count += 1
    return count
