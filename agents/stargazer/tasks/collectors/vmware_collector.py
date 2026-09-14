# -- coding: utf-8 --
# @File: vmware_collector.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
VMware 监控数据采集器
"""
import asyncio
import datetime
from sanic.log import logger
from .base_collector import BaseCollector


def _resource_ip_map(object_id, object_list):
    """ESXi / VM 的 resource_id → ip；其它对象不带 IP。"""
    if object_id not in {"vmware_esxi", "vmware_vm"}:
        return {}
    mapping = {}
    for resource in object_list or ():
        resource_id = resource.get("resource_id")
        ip = str(resource.get("ip_addr") or "").strip()
        if resource_id and ip:
            mapping[resource_id] = ip
    return mapping


def _attach_ip_dimension(metrics, ip):
    """把 ip 写成 convert_to_prometheus 已支持的维度，不改公共转换层。"""
    ip_dim = ("ip", ip)
    attached = {}
    for metric_name, metric_data in (metrics or {}).items():
        if isinstance(metric_data, list):
            attached[metric_name] = {(ip_dim,): metric_data}
        elif isinstance(metric_data, dict):
            attached[metric_name] = {
                (ip_dim,) + tuple(dims): values
                for dims, values in metric_data.items()
            }
        else:
            attached[metric_name] = metric_data
    return attached


class VmwareCollector(BaseCollector):
    """VMware vCenter 监控数据采集器"""

    async def probe(self):
        return await asyncio.to_thread(self._probe_sync)

    def _probe_sync(self):
        from plugins.inputs.vmware_vc.vmware_info import VmwareManage

        manager = VmwareManage(
            params=dict(
                username=self.params.get("username"),
                password=self.params.get("password"),
                hostname=self.params.get("host"),
                ssl=self.params.get("ssl", "false"),
                port=self.params.get("port", 443),
            )
        )
        return manager._probe_sync()

    async def collect(self) -> str:
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> str:
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
        task_id = self.params.get("collection_task_id") or self.params.get("task_id") or ""

        # 获取时间范围
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(minutes=int(minutes))
        start_time_str = start_time.strftime("%Y-%m-%d %H:%M") + ":00"
        end_time_str = end_time.strftime("%Y-%m-%d %H:%M") + ":00"

        try:
            driver = CMPDriver(username, password, "vmware", host=host)
        except ConnectionError as err:
            logger.exception(
                "event=vmware_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                host,
                task_id,
                "create_driver",
                type(err).__name__,
            )
            return ""
        except Exception as err:
            logger.exception(
                "event=vmware_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                host,
                task_id,
                "create_driver",
                type(err).__name__,
            )
            return ""

        try:
            vmware_manager = VmwareManage(params=dict(
                username=username,
                password=password,
                hostname=host,
            ))
            vmware_manager.connect_vc()
            object_map = vmware_manager.service()
        except Exception as err:
            logger.exception(
                "event=vmware_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                host,
                task_id,
                "connect_vc",
                type(err).__name__,
            )
            return ""

        metric_dict = {}
        total_resources_processed = 0
        object_type_count = 0
        object_type_failed = 0

        for object_id, object_list in object_map.items():
            if object_id == "vmware_vc" or not object_list:
                continue

            object_type_count += 1
            ip_by_resource = _resource_ip_map(object_id, object_list)
            resource_ids = [resource["resource_id"] for resource in object_list]
            logger.debug(
                "event=vmware_collect_object_debug host=%s task_id=%s object_type=%s count=%s",
                host,
                task_id,
                object_id,
                len(resource_ids),
            )

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
                    object_type_failed += 1
                    logger.error(
                        "event=vmware_collect_failed host=%s task_id=%s object_type=%s failed_stage=%s error_type=%s",
                        host,
                        task_id,
                        object_id,
                        "get_weops_monitor_data",
                        "result_false",
                    )
                    continue

                for resource_id, metrics in data["data"].items():
                    ip = ip_by_resource.get(resource_id)
                    if ip:
                        metrics = _attach_ip_dimension(metrics, ip)
                    metric_dict[(resource_id, object_id)] = metrics

                total_resources_processed += len(data["data"])
            except Exception as err:
                object_type_failed += 1
                logger.exception(
                    "event=vmware_collect_failed host=%s task_id=%s object_type=%s failed_stage=%s error_type=%s",
                    host,
                    task_id,
                    object_id,
                    "get_weops_monitor_data",
                    type(err).__name__,
                )
                continue

        # 转换为 Prometheus 格式
        metric_list = convert_to_prometheus(metric_dict)
        influxdb_data = "\n".join(metric_list) + "\n"

        logger.info(
            "event=vmware_collect_summary host=%s task_id=%s object_types=%s object_type_failed=%s resources=%s bytes=%s",
            host,
            task_id,
            object_type_count,
            object_type_failed,
            total_resources_processed,
            len(influxdb_data),
        )

        return influxdb_data
