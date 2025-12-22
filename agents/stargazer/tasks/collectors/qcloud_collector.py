# -- coding: utf-8 --
# @File: qcloud_collector.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
QCloud 监控数据采集器
"""
import datetime
from typing import Dict, Any
from sanic.log import logger
from .base_collector import BaseCollector


class QCloudCollector(BaseCollector):
    """腾讯云监控数据采集器"""

    async def collect(self) -> str:
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

        logger.info(f"[QCloud Collector] User={username}, Minutes={minutes}")

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
            logger.info(f"[QCloud Collector] Processing '{object_id}': {len(resource_ids)} resources")

            try:
                data = driver.get_weops_monitor_data(
                    resourceId=",".join(resource_ids),
                    StartTime=start_time_str,
                    EndTime=end_time_str,
                    Period=300,
                    Metrics=[],
                    context={"resources": [{"bk_obj_id": object_id}]}
                )

                if not data["result"]:
                    logger.error(f"[QCloud Collector] Monitor data failed for '{object_id}': {data.get('message')}")
                    continue

                for resource_id, metrics in data["data"].items():
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

