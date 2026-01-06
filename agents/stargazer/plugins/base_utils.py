# -- coding: utf-8 --
# @File: base_utils.py
# @Time: 2025/3/10 18:29
# @Author: windyzhao
import time
import datetime
import ipaddress

import pytz


def convert_to_prometheus_format(data):
    """
    将采集信息转换为Prometheus兼容的文本格式

    输出格式示例：
    # HELP vmware_vc_info Auto-generated help for vmware_vc_info
    # TYPE vmware_vc_info gauge
    vmware_vc_info{inst_name="VMware vCenter Server",vc_version="7.0.3"} 1 1742267662301
    # HELP vmware_ds_info Auto-generated help for vmware_ds_info
    # TYPE vmware_ds_info gauge
    vmware_ds_info{inst_name="datastore1-16.16",resource_id="datastore-1646",storage="2505",system_type="VMFS",
    url="ds:///vmfs/volumes/6385b001-37c96502-d73f-509a4c67b4c3/",vmware_esxi="host-1645"} 1 1742267662301
    ...
    注意：时间戳为13位毫秒级，最后以换行符结尾
    """
    # 生成毫秒级时间戳
    timestamp = int(time.time() * 1000)

    def escape_value(value):
        """转义Prometheus标签值中的特殊字符，同时将非字符串转换为字符串"""
        if isinstance(value, str):
            return value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return str(value)

    # 用于存放所有指标，结构为{metric_name: [line, line, ...]}
    metrics = {}

    # 遍历每个模型，例如：vmware_vc、vmware_ds、vmware_vm、vmware_esxi
    for model_id, items in data.items():
        for item in items:
            # 构造标签字典：过滤掉列表和字典类型，并且值不为None
            labels = {
                k: escape_value(v)
                for k, v in item.items()
                if v and not isinstance(v, (list, dict))
            }
            labels['model_id'] = model_id
            # 按键排序生成标签字符串
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            # 生成info指标，值固定为1，包含所有维度
            info_metric = f"{model_id}_info"
            info_line = f'{info_metric}{{{label_str}}} 1 {timestamp}'
            metrics.setdefault(info_metric, []).append(info_line)

    # 生成输出文本：每个指标输出一次 HELP 和 TYPE 信息，然后输出所有指标行
    output_lines = []
    for metric_name, lines in metrics.items():
        output_lines.append(f"# HELP {metric_name} Auto-generated help for {metric_name}")
        output_lines.append(f"# TYPE {metric_name} gauge")
        output_lines.extend(lines)
    # 确保最后以换行符结尾
    return "\n".join(output_lines) + "\n"


def utc_to_dts(utc_str: str, local_tz="Asia/Shanghai", utc_fmt="%Y-%m-%dT%H:%M:%SZ", fmt="%Y-%m-%d %H:%M:%S") -> str:
    """
    Convert UTC or CST time to local time.
    """
    if not utc_str:
        return ""

    # Check if the input string contains 'CST'
    if "CST" in utc_str:
        utc_fmt = "%Y-%m-%dT%H:%M:%SCST"
        utc_time = datetime.datetime.strptime(utc_str, utc_fmt)
        cst_tz = pytz.timezone("Asia/Shanghai")
        utc_time = cst_tz.localize(utc_time)
    else:
        utc_time = datetime.datetime.strptime(utc_str, utc_fmt)
        utc_time = pytz.UTC.localize(utc_time)

    # Convert to local time
    local_time = utc_time.astimezone(pytz.timezone(local_tz))

    # Convert local time to string
    local_time_str = local_time.strftime(fmt)

    return local_time_str


def ts_to_dts(ts: int, fmt="%Y-%m-%d %H:%M:%S") -> str:
    """
    Convert timestamp to date string.
    """
    if len(str(ts)) == 13:
        ts = ts / 1000
    ts = datetime.datetime.fromtimestamp(ts)
    return ts.strftime(fmt)


def expand_ip_range(ip_range: str) -> list:
    """
    将类似 '192.168.0.1-192.168.0.10' 的网段拆分成单个 IP 地址列表
    """
    try:
        start_str, end_str = ip_range.split('-')
        start_ip = ipaddress.IPv4Address(start_str.strip())
        end_ip = ipaddress.IPv4Address(end_str.strip())
    except Exception as e:
        raise ValueError(f"无效的 IP 网段格式: {ip_range}") from e

    if start_ip > end_ip:
        raise ValueError("起始 IP 不能大于结束 IP")

    ips = [str(ipaddress.IPv4Address(ip)) for ip in range(int(start_ip), int(end_ip) + 1)]
    return ips
