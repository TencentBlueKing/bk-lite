# -- coding: utf-8 --
# @File: vmware_collector.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
VMware 监控数据采集器
"""
import datetime
from sanic.log import logger
from .base_collector import BaseCollector


class VmwareCollector(BaseCollector):
    """VMware vCenter 监控数据采集器"""

    async def collect(self) -> str:
        """
        采集 VMware 监控指标

        Returns:
            Prometheus 格式的指标数据
        """
        from common.cmp.driver import CMPDriver
        from plugins.inputs.vmware_vc.vmware_info import VmwareManage
        from utils.convert import convert_to_prometheus

        username = self.params["username"]
        password = self.params["password"]
        host = self.params["host"]
        minutes = self.params.get("minutes", 5)

        logger.info(f"[VMware Collector] Host={host}, Minutes={minutes}")

        # 获取时间范围
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(minutes=int(minutes))
        start_time_str = start_time.strftime("%Y-%m-%d %H:%M") + ":00"
        end_time_str = end_time.strftime("%Y-%m-%d %H:%M") + ":00"

        logger.info(f"[VMware Collector] Time range: {start_time_str} to {end_time_str}")

        driver = CMPDriver(username, password, "vmware_vc", host=host)

        try:
            vmware_manager = VmwareManage(params=dict(
                username=username,
                password=password,
                hostname=host,
            ))
            vmware_manager.connect_vc()
            object_map = vmware_manager.service()

            total_object_count = sum(len(obj_list) if obj_list else 0 for obj_list in object_map.values())
            logger.info(f"[VMware Collector] Connected: {len(object_map)} object types, {total_object_count} total objects")

        except Exception as e:
            logger.error(f"[VMware Collector] Connection failed: {str(e)}")
            return ""

        metric_dict = {}
        total_resources_processed = 0

        for object_id, object_list in object_map.items():
            if object_id == "vmware_vc" or not object_list:
                continue

            resource_ids = [resource["resource_id"] for resource in object_list]
            logger.info(f"[VMware Collector] Processing '{object_id}': {len(resource_ids)} resources")

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
                    logger.error(f"[VMware Collector] Monitor data failed for '{object_id}': {data.get('message')}")
                    continue

                for resource_id, metrics in data["data"].items():
                    metric_dict[(resource_id, object_id)] = metrics

                total_resources_processed += len(data["data"])
                logger.info(f"[VMware Collector] '{object_id}' processed: {len(data['data'])} resources")

            except Exception as e:
                logger.error(f"[VMware Collector] Error processing '{object_id}': {str(e)}")
                continue

        # 转换为 Prometheus 格式
        metric_list = convert_to_prometheus(metric_dict)
        influxdb_data = "\n".join(metric_list) + "\n"

        logger.info(f"[VMware Collector] Completed: {total_resources_processed} resources, {len(influxdb_data)} bytes")

        return influxdb_data

