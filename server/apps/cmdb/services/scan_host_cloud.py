"""扫描任务 cloud_region → 主机 CI / 采集 params 的 cloud、cloud_name。"""

from __future__ import annotations


def host_cloud_from_scan(scan_task) -> dict:
    """只读任务上的云区域；缺省不填，由调用方决定是否默认 1。"""
    region = getattr(scan_task, "cloud_region", None) if scan_task is not None else None
    if not region:
        return {}
    if isinstance(region, dict):
        cloud = region.get("id")
        if cloud in (None, ""):
            cloud = region.get("cloud_region_id", region.get("cloud"))
        cloud_name = region.get("name") or region.get("cloud_region_name") or region.get("cloud_name") or ""
    elif isinstance(region, int):
        cloud, cloud_name = region, ""
    else:
        text = str(region).strip()
        if not text:
            return {}
        cloud, cloud_name = (int(text), "") if text.isdigit() else (None, text)
    params = {}
    if cloud not in (None, ""):
        params["cloud"] = cloud
    if cloud_name:
        params["cloud_name"] = cloud_name
    return params
