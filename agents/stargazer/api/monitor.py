import datetime

from core.config import YamlConfig
from common.cmp.driver import CMPDriver
from sanic import Blueprint
from sanic.log import logger
from sanic import response

from plugins.vmware_info import VmwareManage
from utils.convert import convert_to_prometheus

yml_config = YamlConfig(path="./config.yml")

monitor_router = Blueprint("monitor", url_prefix="/monitor")


def get_config(monitor_type: str, monitor_instance: str):
    """
    Get the configuration for the monitor type and instance
    :param monitor_type:
    :param monitor_instance:
    :return: dict
    """
    config = yml_config.get(monitor_type, {}).get(monitor_instance, {})
    return config


def get_time_range(minutes: int):
    """
    Get the start and end time based on the current time and given minutes
    :param minutes: int, number of minutes to go back from current time
    :return: tuple (start_time, end_time)
    """
    end_time = datetime.datetime.now()
    start_time = end_time - datetime.timedelta(minutes=int(minutes))
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M") + ":00"
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M") + ":00"
    return start_time_str, end_time_str


def analyze_metrics_data(metrics, metrics_detail, resource_metrics_count):
    """
    分析指标数据并统计详细信息
    :param metrics: 指标数据
    :param metrics_detail: 指标详细统计字典
    :param resource_metrics_count: 资源指标计数
    :return: 更新后的指标计数
    """
    if isinstance(metrics, list):
        resource_metrics_count += len(metrics)
        # 记录列表中每个指标的详情
        for metric in metrics:
            if isinstance(metric, dict) and 'MetricName' in metric:
                metric_name = metric['MetricName']
                metrics_detail[metric_name] = metrics_detail.get(metric_name, 0) + 1
            elif isinstance(metric, dict):
                # 如果没有MetricName，尝试其他可能的键
                found_metric = False
                for key in metric.keys():
                    if 'metric' in key.lower() or 'name' in key.lower():
                        metric_name = metric.get(key, 'unknown_metric')
                        metrics_detail[metric_name] = metrics_detail.get(metric_name, 0) + 1
                        found_metric = True
                        break
                if not found_metric:
                    metrics_detail['unknown_metric'] = metrics_detail.get('unknown_metric', 0) + 1
    elif isinstance(metrics, dict):
        resource_metrics_count += len(metrics)
        # 记录字典中每个指标的详情
        for metric_name, metric_data in metrics.items():
            if isinstance(metric_data, list):
                metrics_detail[metric_name] = metrics_detail.get(metric_name, 0) + len(metric_data)
            else:
                metrics_detail[metric_name] = metrics_detail.get(metric_name, 0) + 1
    else:
        resource_metrics_count += 1
        metrics_detail['unknown_metric'] = metrics_detail.get('unknown_metric', 0) + 1

    return resource_metrics_count


def log_metrics_summary(object_id, metrics_detail, resources_count, metrics_count):
    """
    记录指标汇总信息
    """
    if metrics_detail:
        logger.info(f"'{object_id}' - {resources_count} resources, {metrics_count} metrics:")
        for metric_name, count in sorted(metrics_detail.items()):
            logger.info(f"  - {metric_name}: {count} data points")
    else:
        logger.warning(f"'{object_id}' has no identifiable metrics")


@monitor_router.get("/vmware/metrics")
async def vmware_metrics(request):
    logger.info("=== VMware metrics collection started ===")

    username = request.headers.get("username")
    password = request.headers.get("password")
    host = request.headers.get("host")
    minutes = request.args.get("minutes", 5)

    logger.info(f"Request: Host={host}, Minutes={minutes}, User={username}")

    driver = CMPDriver(username, password, "vmware", host=host)
    start_time_str, end_time_str = get_time_range(int(minutes))
    logger.info(f"Time range: {start_time_str} to {end_time_str}")

    try:
        object_map = VmwareManage(params=dict(
            username=username,
            password=password,
            hostname=host,
        )).service()

        total_object_count = sum(len(obj_list) if obj_list else 0 for obj_list in object_map.values())
        logger.info(f"VMware connected: {len(object_map)} object types, {total_object_count} total objects")

    except Exception as e:
        logger.error(f"VMware connection failed: {str(e)}")
        return response.json({"error": "VMware connection failed", "message": str(e)}, status=500)

    metric_dict = {}
    total_resources_processed = 0
    total_metrics_collected = 0

    for object_id, object_list in object_map.items():
        if object_id == "vmware_vc" or not object_list:
            continue

        resource_ids = [resource["resource_id"] for resource in object_list]
        logger.info(f"Processing '{object_id}': {len(resource_ids)} resources")

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
                logger.error(f"Monitor data failed for '{object_id}': {data.get('message')}")
                continue

            # 统计指标详细信息
            resource_metrics_count = 0
            metrics_detail = {}

            for resource_id, metrics in data["data"].items():
                metric_dict[(resource_id, object_id)] = metrics
                resource_metrics_count = analyze_metrics_data(metrics, metrics_detail, resource_metrics_count)

            # 记录汇总信息
            log_metrics_summary(object_id, metrics_detail, len(data["data"]), resource_metrics_count)

            total_resources_processed += len(data["data"])
            total_metrics_collected += resource_metrics_count

        except Exception as e:
            logger.error(f"Error processing '{object_id}': {str(e)}")
            continue

    # 转换为Prometheus格式
    metric_list = convert_to_prometheus(metric_dict)
    influxdb_data = "\n".join(metric_list) + "\n"

    logger.info(f"Collection completed: {total_resources_processed} resources, {total_metrics_collected} metrics, {len(influxdb_data)} bytes")
    logger.info("=== VMware metrics collection finished ===")

    return response.raw(influxdb_data, content_type='text/plain; version=0.0.4; charset=utf-8')


@monitor_router.get("/qcloud/metrics")
async def qcloud_metrics(request):
    logger.info("=== QCloud metrics collection started ===")

    username = request.headers.get("username")
    password = request.headers.get("password")
    minutes = request.args.get("minutes", 5)

    logger.info(f"Request: Minutes={minutes}, User={username}")

    driver = CMPDriver(username, password, "qcloud")
    start_time_str, end_time_str = get_time_range(int(minutes))
    logger.info(f"Time range: {start_time_str} to {end_time_str}")

    try:
        all_resources = driver.list_all_resources()

        if not all_resources.get("data"):
            logger.warning("No resources found in QCloud")
            return response.raw("", content_type='text/plain; version=0.0.4; charset=utf-8')

        total_resource_count = sum(len(resources) if resources else 0 for resources in all_resources.get("data", {}).values())
        logger.info(f"QCloud connected: {len(all_resources.get('data', {}))} object types, {total_resource_count} total resources")

    except Exception as e:
        logger.error(f"QCloud resource fetch failed: {str(e)}")
        return response.json({"error": "QCloud resource fetch failed", "message": str(e)}, status=500)

    metric_dict = {}
    total_resources_processed = 0
    total_metrics_collected = 0

    for object_id, resources in all_resources.get("data", {}).items():
        if not resources:
            continue

        resource_ids = [resource["resource_id"] for resource in resources]
        logger.info(f"Processing '{object_id}': {len(resource_ids)} resources")

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
                logger.error(f"Monitor data failed for '{object_id}': {data.get('message')}")
                continue

            # 统计指标详细信息
            resource_metrics_count = 0
            metrics_detail = {}

            for resource_id, metrics in data["data"].items():
                metric_dict[(resource_id, object_id)] = metrics
                resource_metrics_count = analyze_metrics_data(metrics, metrics_detail, resource_metrics_count)

            # 记录汇总信息
            log_metrics_summary(object_id, metrics_detail, len(data["data"]), resource_metrics_count)

            total_resources_processed += len(data["data"])
            total_metrics_collected += resource_metrics_count

        except Exception as e:
            logger.error(f"Error processing '{object_id}': {str(e)}")
            continue

    # 转换为Prometheus格式
    metric_list = convert_to_prometheus(metric_dict)
    influxdb_data = "\n".join(metric_list) + "\n"

    logger.info(f"Collection completed: {total_resources_processed} resources, {total_metrics_collected} metrics, {len(influxdb_data)} bytes")
    logger.info("=== QCloud metrics collection finished ===")

    return response.raw(influxdb_data, content_type='text/plain; version=0.0.4; charset=utf-8')
