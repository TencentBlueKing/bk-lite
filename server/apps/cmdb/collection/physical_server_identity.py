import ipaddress


def normalize_physical_server_ip(value) -> str:
    """把物理服务器采集目标规范成稳定的实例名。"""
    target = str(value or "").strip()
    if not target:
        return ""
    try:
        return str(ipaddress.ip_address(target))
    except ValueError:
        # 存量任务可能保存主机名；保持可用且让三种采集方式得到同一结果。
        return target.lower()


def resolve_physical_server_inst_name(data, fallback="") -> str:
    """实例名只取采集目标 IP，不使用序列号、型号等返回字段。"""
    source = data if isinstance(data, dict) else {}
    for key in ("collection_target", "host", "ip_addr"):
        value = normalize_physical_server_ip(source.get(key))
        if value:
            return value
    return normalize_physical_server_ip(fallback)
