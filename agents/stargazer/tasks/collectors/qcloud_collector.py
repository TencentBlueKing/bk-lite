# -- coding: utf-8 --
# @File: qcloud_collector.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
QCloud 监控数据采集器
"""
import asyncio
import datetime

from sanic.log import logger

from .base_collector import BaseCollector

QCLOUD_CVM_OBJECT_ID = "qcloud_cvm"


def _flatten_ip_values(value):
    """展开列表/字符串中的 IP，去掉空白和空值。"""
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten_ip_values(item)
        return
    ip = str(value).strip()
    if ip:
        yield ip


def _join_cvm_ips(resource):
    """优先内网 IP，其次公网 IP；去重并保持原顺序，逗号拼接。"""
    ips = []
    seen = set()
    for value in (resource.get("inner_ip"), resource.get("public_ip")):
        for ip in _flatten_ip_values(value):
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)
    return ",".join(ips)


def _cvm_resource_ip_map(resources):
    """qcloud_cvm 的 resource_id → IP；无 IP 的资源不入表。"""
    mapping = {}
    for resource in resources or ():
        resource_id = resource.get("resource_id")
        ip = _join_cvm_ips(resource)
        if resource_id and ip:
            mapping[resource_id] = ip
    return mapping


def _attach_ip_dimension(metrics, ip):
    """把 resource_ip 写成 convert_to_prometheus 已支持的维度，不改公共转换层。"""
    ip_dim = ("resource_ip", ip)
    attached = {}
    for metric_name, metric_data in (metrics or {}).items():
        if isinstance(metric_data, list):
            attached[metric_name] = {(ip_dim,): metric_data}
        elif isinstance(metric_data, dict):
            attached[metric_name] = {(ip_dim,) + tuple(dims): values for dims, values in metric_data.items()}
        else:
            attached[metric_name] = metric_data
    return attached


class QCloudCollector(BaseCollector):
    """腾讯云监控数据采集器"""

    async def collect(self) -> str:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> str:
        """
        采集 QCloud 监控指标

        Returns:
            Prometheus 格式的指标数据
        """
        from common.cmp.driver import CMPDriver
        from utils.convert import convert_to_prometheus

        username = self.params["username"]
        password = self.params["password"]
        minutes = self.params.get("minutes", 5)

        logger.info(f"[QCloud Collector] Minutes={minutes}")

        # 获取时间范围
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(minutes=int(minutes))
        start_time_str = start_time.strftime("%Y-%m-%d %H:%M") + ":00"
        end_time_str = end_time.strftime("%Y-%m-%d %H:%M") + ":00"

        logger.info(f"[QCloud Collector] Time range: {start_time_str} to {end_time_str}")

        driver = CMPDriver(username, password, "qcloud")

        try:
            all_resources = driver.list_all_resources()

            if not all_resources.get("data"):
                logger.warning("[QCloud Collector] No resources found")
                return ""

            total_resource_count = sum(len(resources) if resources else 0 for resources in all_resources.get("data", {}).values())
            logger.info(f"[QCloud Collector] Connected: {len(all_resources.get('data', {}))} object types, {total_resource_count} total resources")

        except Exception as e:
            logger.error(f"[QCloud Collector] Resource fetch failed: {str(e)}")
            raise

        metric_dict = {}
        total_resources_processed = 0

        for object_id, resources in all_resources.get("data", {}).items():
            if not resources:
                continue

            resource_ids = [resource["resource_id"] for resource in resources]
            ip_by_resource = _cvm_resource_ip_map(resources) if object_id == QCLOUD_CVM_OBJECT_ID else {}
            logger.info(f"[QCloud Collector] Processing '{object_id}': {len(resource_ids)} resources")

            try:
                data = driver.get_weops_monitor_data(
                    resourceId=",".join(resource_ids),
                    StartTime=start_time_str,
                    EndTime=end_time_str,
                    Period=300,
                    Metrics=[],
                    context={"resources": [{"bk_obj_id": object_id}]},
                )

                if not data["result"]:
                    logger.error(f"[QCloud Collector] Monitor data failed for '{object_id}': {data.get('message')}")
                    continue

                for resource_id, metrics in data["data"].items():
                    ip = ip_by_resource.get(resource_id)
                    if ip:
                        metrics = _attach_ip_dimension(metrics, ip)
                    metric_dict[(resource_id, object_id)] = metrics

                total_resources_processed += len(data["data"])
                logger.info(f"[QCloud Collector] '{object_id}' processed: {len(data['data'])} resources")

            except Exception as e:
                logger.error(f"[QCloud Collector] Error processing '{object_id}': {str(e)}")
                continue

        # 转换为 Prometheus 格式
        metric_list = convert_to_prometheus(metric_dict)
        influxdb_data = "\n".join(metric_list) + "\n"

        logger.info(f"[QCloud Collector] Completed: {total_resources_processed} resources, {len(influxdb_data)} bytes")

        return influxdb_data
