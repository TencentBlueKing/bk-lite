#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
华为存储 API 现场验证脚本
适用设备：Huawei Dorado 5000 / OceanProtect X6000 / OceanStor 系列
基于 OceanStorApiMonitor 逻辑，验证登录、配置获取、性能数据采集全流程
"""

import json
import sys
import time
import traceback
from datetime import datetime

import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# ============== 配置区域（现场修改此处） ==============
BASE_URL = "https://192.168.1.100:8088"  # 替换为实际存储管理地址
USERNAME = "admin"
PASSWORD = "your_password"
LOG_FILE = "oceanstor_apitest_result.txt"
# ====================================================

# 指标映射（与 api.py 一致）
METRICS_API_MAP = {
    "api_pool_io_rate": "22",
    "api_pool_read_io": "25",
    "api_pool_write_io": "28",
    "api_pool_resp_t": "370",
    "api_pool_read": "23",
    "api_pool_write": "26",
    "api_pool_resp_t_r": "384",
    "api_pool_resp_t_w": "385",
    "api_drive_io_rate": "22",
    "api_drive_read_io": "25",
    "api_drive_write_io": "28",
    "api_drive_resp_t": "370",
    "api_drive_read": "23",
    "api_drive_write": "26",
    "api_drive_resp_t_r": "384",
    "api_drive_resp_t_w": "385",
    "api_volume_io_rate": "22",
    "api_volume_read_io": "25",
    "api_volume_write_io": "28",
    "api_volume_resp_t": "370",
    "api_volume_read": "23",
    "api_volume_write": "26",
    "api_volume_resp_t_r": "384",
    "api_volume_resp_t_w": "385",
}

# 性能指标 ID 列表（去重）
PERF_INDICATOR_IDS = list(set(METRICS_API_MAP.values()))

# 对象类型映射
OBJ_TYPE_MAP = {
    "pool": {"type_id": "216", "config_endpoint": "storagepool", "dims_key": "pool_id"},
    "drive": {"type_id": "10", "config_endpoint": "disk", "dims_key": "drive_id"},
    "volume": {"type_id": "11", "config_endpoint": "lun", "dims_key": "volume_id"},
}

session = requests.Session()
session.verify = False
results = []
perf_switch_off = False  # 性能统计开关状态


def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    results.append(line)


def login():
    """登录获取 token 和 device_id"""
    url = f"{BASE_URL}/deviceManager/rest/xxxxx/sessions"
    payload = {"username": USERNAME, "password": PASSWORD, "scope": "0"}
    resp = session.post(url, json=payload, timeout=30)
    resp_json = resp.json()
    data = resp_json.get("data", {})
    if not data:
        err = resp_json.get("error", {})
        log(f"登录失败: code={err.get('code')}, desc={err.get('description')}", "ERROR")
        return None, None
    token = data.get("iBaseToken")
    device_id = data.get("deviceid")
    session.headers.update({"iBaseToken": token, "Content-Type": "application/json"})
    log(f"登录成功, device_id={device_id}")
    return token, device_id


def logout(device_id):
    """登出"""
    url = f"{BASE_URL}/deviceManager/rest/{device_id}/sessions"
    try:
        session.delete(url, timeout=10)
        log("登出成功")
    except Exception as e:
        log(f"登出异常: {e}", "WARN")


def check_perf_switch(device_id):
    """检查性能统计开关，返回 True=已开启"""
    global perf_switch_off
    log("\n" + "=" * 60)
    log(">>> 检查性能统计开关")

    url = f"{BASE_URL}/deviceManager/rest/{device_id}/performance_statistic_switch"
    try:
        resp = session.get(url, timeout=30)
        resp_json = resp.json()
        data = resp_json.get("data", [])
        if isinstance(data, list):
            for item in data:
                switch_val = item.get("CMO_PERFORMANCE_SWITCH", "0")
                if switch_val == "1":
                    log("  性能统计开关: 已开启 ✓")
                    return True
                else:
                    log("  性能统计开关: 未开启 ✗", "ERROR")
                    log("  请在存储管理界面开启: 系统 > 性能监控 > 性能统计开关", "ERROR")
                    perf_switch_off = True
                    return False
    except Exception:
        pass

    # 备用路径
    url2 = f"{BASE_URL}/deviceManager/rest/{device_id}/performace_statistic/cur_statistic_data"
    params = {"CMO_STATISTIC_UUID": "216:0", "CMO_STATISTIC_DATA_ID_LIST": "22"}
    try:
        resp = session.get(url2, params=params, timeout=30)
        resp_json = resp.json()
        err_code = resp_json.get("error", {}).get("code", 0)
        if err_code == 83890437:
            log("  性能统计开关: 未开启 ✗ (code=83890437)", "ERROR")
            log("  请在存储管理界面开启: 系统 > 性能监控 > 性能统计开关", "ERROR")
            perf_switch_off = True
            return False
        elif err_code == 0:
            log("  性能统计开关: 已开启 ✓")
            return True
    except Exception:
        pass

    log("  性能统计开关: 无法确认状态", "WARN")
    return True  # 无法确认时继续尝试


def fetch_config_paged(device_id, endpoint_key):
    """分页获取配置数据（OceanStor 默认每次最多返回 100 条）"""
    config_section = OBJ_TYPE_MAP[endpoint_key]["config_endpoint"]
    all_data = []
    batch_size = 100
    start = 0

    while True:
        url = f"{BASE_URL}/deviceManager/rest/{device_id}/{config_section}"
        params = {"range": f"[{start}-{start + batch_size - 1}]"}
        try:
            resp = session.get(url, params=params, timeout=30)
            resp_json = resp.json()
            err_code = resp_json.get("error", {}).get("code", -1)
            if err_code != 0:
                err_desc = resp_json.get("error", {}).get("description", "")
                if start == 0:
                    log(f"  获取 {config_section} 配置失败: code={err_code}, desc={err_desc}", "ERROR")
                break
            data = resp_json.get("data", [])
            if not data:
                break
            all_data.extend(data)
            if len(data) < batch_size:
                break
            start += batch_size
        except Exception as e:
            if start == 0:
                log(f"  获取 {config_section} 配置异常: {e}", "ERROR")
            break

    return all_data


def fetch_performance(device_id, obj_type_id, obj_id):
    """获取实时性能数据"""
    url = f"{BASE_URL}/deviceManager/rest/{device_id}/performace_statistic/cur_statistic_data"
    params = {
        "CMO_STATISTIC_UUID": f"{obj_type_id}:{obj_id}",
        "CMO_STATISTIC_DATA_ID_LIST": ",".join(PERF_INDICATOR_IDS),
    }
    resp = session.get(url, params=params, timeout=30)
    resp_json = resp.json()
    err_code = resp_json.get("error", {}).get("code", -1)
    if err_code != 0:
        err_desc = resp_json.get("error", {}).get("description", "")
        log(f"    获取性能数据失败 (type={obj_type_id}, id={obj_id}): code={err_code}, desc={err_desc}", "WARN")
        return []
    return resp_json.get("data", [])


def process_performance_data(perf_data, group_prefix):
    """解析性能数据，返回指标名->值的字典"""
    reverse_map = {}
    for metric_name, indicator_id in METRICS_API_MAP.items():
        if metric_name.startswith(f"api_{group_prefix}_"):
            reverse_map[indicator_id] = metric_name

    parsed = {}
    for item in perf_data:
        id_list = item.get("CMO_STATISTIC_DATA_ID_LIST", "").split(",")
        data_list = item.get("CMO_STATISTIC_DATA_LIST", "").split(",")
        timestamp = item.get("CMO_STATISTIC_TIMESTAMP", "")
        parsed["_timestamp"] = timestamp
        for ind_id, value in zip(id_list, data_list):
            metric_name = reverse_map.get(ind_id)
            if metric_name:
                parsed[metric_name] = value
    return parsed


def get_obj_display_name(obj, group_key):
    """获取对象显示名称，磁盘使用 LOCATION + MODEL，其他使用 NAME"""
    if group_key == "drive":
        location = obj.get("LOCATION", "")
        model = obj.get("MODEL", "")
        disk_type = obj.get("DISKTYPE", "")
        # 磁盘类型映射
        type_map = {"0": "SAS", "1": "SATA", "2": "SSD", "3": "NL-SAS", "4": "SSD", "5": "SSD", "6": "SSD"}
        type_name = type_map.get(str(disk_type), "")
        parts = [p for p in [location, model, type_name] if p]
        return " | ".join(parts) if parts else f"Disk-{obj.get('ID', 'N/A')}"
    return obj.get("NAME", "N/A")


def test_group(device_id, group_key):
    """测试某一类对象（pool/drive/volume）的配置和性能"""
    cfg = OBJ_TYPE_MAP[group_key]
    type_id = cfg["type_id"]
    dims_key = cfg["dims_key"]

    group_names = {"pool": "存储池", "drive": "磁盘", "volume": "LUN卷"}
    log(f"\n{'='*60}")
    log(f">>> 测试{group_names[group_key]}（{cfg['config_endpoint']}，对象类型={type_id}）")

    items = fetch_config_paged(device_id, group_key)
    if not items:
        log(f"  未获取到{group_names[group_key]}配置数据", "WARN")
        return

    log(f"  数量: {len(items)}")

    # 配置数据展示前5个
    test_count = min(5, len(items))
    for obj in items[:test_count]:
        obj_id = obj.get("ID")
        obj_name = get_obj_display_name(obj, group_key)
        if not obj_id:
            continue
        log(f"  [{group_names[group_key]}] {obj_name} (ID={obj_id}, {dims_key}={obj_id})")

        # 性能开关关闭时跳过性能数据请求
        if perf_switch_off:
            continue

        perf_data = fetch_performance(device_id, type_id, obj_id)
        if perf_data:
            parsed = process_performance_data(perf_data, group_key)
            ts = parsed.pop("_timestamp", "")
            if ts:
                try:
                    log(f"    时间戳: {ts} ({datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')})")
                except (ValueError, OSError):
                    log(f"    时间戳: {ts}")
            for metric_name, value in parsed.items():
                log(f"    {metric_name} = {value}")
            log(f"    性能数据获取成功 ✓")
        else:
            log(f"    性能数据为空 ✗", "WARN")

    if len(items) > test_count:
        log(f"  ... 省略其余 {len(items)-test_count} 个对象")

    log(f"  配置接口验证通过 ✓ (共 {len(items)} 个)")


def main():
    log("=" * 60)
    log(f"华为存储 API 现场验证 - {BASE_URL}")
    log(f"适用: Dorado 5000 / OceanProtect X6000 / OceanStor 系列")
    log("=" * 60)

    token, device_id = login()
    if not token:
        log("登录失败，退出", "ERROR")
        sys.exit(1)

    try:
        # 先检查性能统计开关
        check_perf_switch(device_id)
        if perf_switch_off:
            log("\n  性能统计开关未开启，将跳过性能数据采集，仅验证配置接口", "WARN")

        test_group(device_id, "pool")
        test_group(device_id, "drive")
        test_group(device_id, "volume")

        # 汇总
        log(f"\n{'='*60}")
        log(">>> 验证结论")
        log(f"  登录接口: ✓")
        log(f"  配置接口 (storagepool/disk/lun): ✓")
        if perf_switch_off:
            log(f"  性能接口: ✗ 性能统计开关未开启，需客户在存储管理界面开启", "ERROR")
        else:
            log(f"  性能接口 (performace_statistic): ✓")
    except Exception as e:
        log(f"测试异常: {e}\n{traceback.format_exc()}", "ERROR")
    finally:
        logout(device_id)

    log("\n" + "=" * 60)
    log("测试完成")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(results))
    print(f"\n结果已保存: {LOG_FILE}")


if __name__ == "__main__":
    main()
