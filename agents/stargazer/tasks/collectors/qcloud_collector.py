# -- coding: utf-8 --
# @File: qcloud_collector.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
QCloud 监控数据采集器
"""
import asyncio
import datetime
import time

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


def _parse_qcloud_regions(value):
    """表单多选为列表，Telegraf header 为逗号串；空值回落广州。"""
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
    else:
        parts = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return parts or ["ap-guangzhou"]


def _latest_sample(values):
    """保留时间戳最大的一个点；并列时用后面的点。"""
    latest = None
    for item in values or ():
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        timestamp, value = item
        if latest is None or (timestamp or 0) >= (latest[0] or 0):
            latest = (timestamp, value)
    return latest


def _restamp_metrics(metrics, timestamp_ms):
    """云监控周期点改写为当前毫秒，否则样本必然落在 5 分钟瞬时查询窗口外。"""
    restamped = {}
    for metric_name, metric_data in (metrics or {}).items():
        if isinstance(metric_data, dict):
            dim_samples = {}
            for dims, values in metric_data.items():
                latest = _latest_sample(values)
                if latest is not None:
                    dim_samples[dims] = [[timestamp_ms, latest[1]]]
            if dim_samples:
                restamped[metric_name] = dim_samples
        elif isinstance(metric_data, list):
            latest = _latest_sample(metric_data)
            if latest is not None:
                restamped[metric_name] = [[timestamp_ms, latest[1]]]
        else:
            restamped[metric_name] = metric_data
    return restamped


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
        host = self.params.get("host") or ""
        task_id = self.params.get("collection_task_id") or self.params.get("task_id") or ""
        # 与 API 缺省一致：旧配置未传地域时仍采广州，避免无数据行为突变。
        regions = _parse_qcloud_regions(self.params.get("region"))

        # 获取时间范围
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(minutes=int(minutes))
        start_time_str = start_time.strftime("%Y-%m-%d %H:%M") + ":00"
        end_time_str = end_time.strftime("%Y-%m-%d %H:%M") + ":00"

        metric_dict = {}
        total_resources_processed = 0
        listed_ok = False
        object_type_count = 0
        object_type_failed = 0

        for region in regions:
            driver = CMPDriver(username, password, "qcloud", region=region)
            try:
                all_resources = driver.list_all_resources()
            except Exception as err:
                logger.exception(
                    "event=qcloud_collect_failed host=%s task_id=%s region=%s failed_stage=%s error_type=%s",
                    host,
                    task_id,
                    region,
                    "list_all_resources",
                    type(err).__name__,
                )
                continue

            listed_ok = True
            if not all_resources.get("data"):
                logger.warning(
                    "event=qcloud_collect_empty host=%s task_id=%s region=%s failed_stage=%s",
                    host,
                    task_id,
                    region,
                    "list_all_resources",
                )
                continue

            for object_id, resources in all_resources.get("data", {}).items():
                if not resources:
                    continue

                object_type_count += 1
                resource_ids = [resource.get("resource_id") for resource in resources if resource.get("resource_id")]
                if not resource_ids:
                    logger.warning(
                        "event=qcloud_collect_skip host=%s task_id=%s region=%s object_type=%s failed_stage=%s",
                        host,
                        task_id,
                        region,
                        object_id,
                        "missing_resource_id",
                    )
                    continue
                ip_by_resource = _cvm_resource_ip_map(resources) if object_id == QCLOUD_CVM_OBJECT_ID else {}
                logger.debug(
                    "event=qcloud_collect_object_debug host=%s task_id=%s region=%s object_type=%s count=%s",
                    host,
                    task_id,
                    region,
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
                        context={"resources": [{"bk_obj_id": object_id}]},
                    )

                    if not data["result"]:
                        object_type_failed += 1
                        logger.error(
                            "event=qcloud_collect_failed host=%s task_id=%s region=%s object_type=%s failed_stage=%s error_type=%s",
                            host,
                            task_id,
                            region,
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
                        "event=qcloud_collect_failed host=%s task_id=%s region=%s object_type=%s failed_stage=%s error_type=%s",
                        host,
                        task_id,
                        region,
                        object_id,
                        "get_weops_monitor_data",
                        type(err).__name__,
                    )
                    continue

        publish_ms = int(time.time() * 1000)
        metric_dict = {key: _restamp_metrics(metrics, publish_ms) for key, metrics in metric_dict.items()}
        metric_list = convert_to_prometheus(metric_dict) if metric_dict else []
        connect_lines = self._connect_status_lines(connected=listed_ok, timestamp_ms=publish_ms)
        influxdb_data = "\n".join(connect_lines + metric_list) + "\n"

        logger.info(
            "event=qcloud_collect_summary host=%s task_id=%s object_types=%s object_type_failed=%s resources=%s bytes=%s connected=%s",
            host,
            task_id,
            object_type_count,
            object_type_failed,
            total_resources_processed,
            len(influxdb_data),
            listed_ok,
        )

        return influxdb_data

    def _connect_status_lines(self, *, connected: bool, timestamp_ms: int | None = None) -> list[str]:
        """账号级连通性。NATS 会把 Prometheus gauge 写成 ConnectStatus_gauge。"""
        tags = self.params.get("tags") if isinstance(self.params.get("tags"), dict) else {}
        instance_id = tags.get("instance_id") or self.params.get("instance_id") or "qcloud"
        safe_instance_id = str(instance_id).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        value = 1 if connected else 0
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        return [
            "# HELP ConnectStatus QCloud API connectivity",
            "# TYPE ConnectStatus gauge",
            (f'ConnectStatus{{instance_id="{safe_instance_id}",' f'instance_type="qcloud"}} {value} {timestamp_ms}'),
        ]
