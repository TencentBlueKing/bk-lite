# -- coding: utf-8 --
# @File: nats_helper.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
NATS 推送辅助工具
处理指标数据推送到 NATS（InfluxDB Line Protocol 格式）
"""
import os
import re
import traceback
from typing import Dict, Any
from sanic.log import logger
from influxdb_client import Point, WritePrecision
from core.nats import NATSClient, NATSConfig


async def publish_metrics_to_nats(
    ctx: Dict,
    metrics_data: str,
    params: Dict[str, Any],
    task_id: str
):
    """
    将采集结果推送到 NATS 的 metrics 主题

    推送格式：InfluxDB Line Protocol（与 Telegraf 保持一致）
    每条指标数据单独发送一次消息

    Args:
        ctx: ARQ 上下文
        metrics_data: Prometheus 格式的指标数据
        params: 采集参数（包含 tags）
        task_id: 任务ID
    """
    try:
        # 获取 NATS Metric Topic 前缀（从环境变量读取，默认为 metrics）
        metric_topic_prefix = os.getenv('NATS_METRIC_TOPIC', 'metrics')

        # 获取任务类型（monitor_type 或 plugin_name）
        task_type = params.get('monitor_type') or params.get(
            'plugin_name', params.get("model_id", "unknown"))

        # 构建 subject: {prefix}.{task_type}
        # 例如: metrics.vmware, metrics.mysql, metrics.host 等
        subject = f"{metric_topic_prefix}.{task_type}"

        logger.info(
            f"[NATS Helper] Preparing to publish to subject: {subject}")

        # 将 Prometheus 格式转换为 InfluxDB Line Protocol 格式
        influx_lines = convert_prometheus_to_influx(metrics_data, params)

        if not influx_lines:
            logger.warning(
                f"[NATS Helper] No data to publish for task {task_id}")
            return

        # 统计信息
        total_lines = len(influx_lines)
        total_bytes = sum(len(line.encode('utf-8')) for line in influx_lines)

        logger.info(
            f"[NATS Helper] Converted {len(metrics_data)} bytes Prometheus data to {total_lines} lines ({total_bytes} bytes)")

        # 打印前3行指标数据预览
        preview_count = min(3, len(influx_lines))
        if preview_count > 0:
            logger.info(
                f"[NATS Helper] Metrics preview (first {preview_count} lines):")
            for i, line in enumerate(influx_lines[:preview_count], 1):
                logger.info(
                    f"[NATS Helper]   {i}. {line[:150]}{'...' if len(line) > 150 else ''}")
            if total_lines > preview_count:
                logger.info(
                    f"[NATS Helper] ... and {total_lines - preview_count} more lines")

        # 创建 NATS 配置
        nats_config = NATSConfig.from_env()
        logger.info(
            f"[NATS Helper] NATS config: servers={nats_config.servers}, tls_enabled={nats_config.tls_enabled}, user={nats_config.user}")

        # 使用 async with 自动管理连接
        try:
            logger.info(f"[NATS Helper] Attempting to connect to NATS...")
            async with NATSClient(nats_config) as nats_client:
                logger.info(
                    f"[NATS Helper] NATS client connected: {nats_client.is_connected}")

                # 检查连接状态
                if not nats_client.nc:
                    raise ConnectionError(
                        "NATS client nc is None after connect")

                if nats_client.nc.is_closed:
                    raise ConnectionError("NATS connection is closed")

                # 逐行发送消息（与 Telegraf 保持一致）
                success_count = 0
                for line in influx_lines:
                    try:
                        await nats_client.nc.publish(subject, line.encode('utf-8'))
                        success_count += 1
                    except Exception as pub_err:
                        logger.error(
                            f"[NATS Helper] Failed to publish line: {line[:100]}, error: {pub_err}")

                logger.info(
                    f"[NATS Helper] Successfully published {success_count}/{total_lines} metrics to '{subject}' for task {task_id}")

                if success_count < total_lines:
                    logger.warning(
                        f"[NATS Helper] Failed to publish {total_lines - success_count} metrics")

        except ConnectionError as ce:
            logger.error(f"[NATS Helper] Connection error: {ce}")
            raise
        except Exception as conn_err:
            logger.error(
                f"[NATS Helper] Failed to connect to NATS: {conn_err}\n{traceback.format_exc()}")
            raise

    except Exception as e:
        logger.error(
            f"[NATS Helper] Failed to publish metrics: {e}\n{traceback.format_exc()}")


def convert_prometheus_to_influx(prometheus_data: str, params: Dict[str, Any]) -> list:
    """
    将 Prometheus 格式转换为 InfluxDB Line Protocol 格式

    使用 influxdb_client.Point 类来构建 Line Protocol，提供：
    - 自动类型处理（整数、浮点数、字符串）
    - 自动转义特殊字符（空格、逗号、等号等）
    - 更清晰的对象化 API

    Prometheus 格式:
        # TYPE metric_name gauge
        metric_name{label1="value1",label2="value2"} value timestamp

    InfluxDB Line Protocol 格式:
        metric_name,tag1=value1,tag2=value2 gauge=value timestamp
        (field 名称从 TYPE 注释中提取，保持与 Telegraf 行为一致)

    Args:
        prometheus_data: Prometheus 格式的指标数据
        params: 采集参数（包含从 API 传递的 tags）

    Returns:
        InfluxDB Line Protocol 格式的数据列表（每行一条）
    """
    if not prometheus_data or not prometheus_data.strip():
        return []

    lines = []

    # 获取通用 tags（从 API 传递的参数，已清理特殊字符）
    common_tags = _build_common_tags(params)

    # 用于记录每个指标的类型（从 TYPE 注释中提取）
    metric_types = {}  # {metric_name: field_type}
    current_type = None

    # 预处理：合并多行数据（处理标签值中的换行符 \n）
    prometheus_lines = []
    current_line = ""
    for line in prometheus_data.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 如果是注释行或新的指标行（不以 \ 开头），则保存之前的行
        if line.startswith('#') or (current_line and not line.startswith('\\')):
            if current_line:
                prometheus_lines.append(current_line)
            current_line = line
        else:
            # 续行：拼接到当前行
            current_line += ' ' + line

    # 添加最后一行
    if current_line:
        prometheus_lines.append(current_line)

    for line in prometheus_lines:
        # 解析 TYPE 注释，提取指标类型
        if line.startswith('# TYPE '):
            # 格式: # TYPE metric_name gauge|counter|histogram|summary
            parts = line.split()
            if len(parts) >= 4:
                metric_name = parts[2]
                metric_type = parts[3]  # gauge, counter, histogram, summary 等
                metric_types[metric_name] = metric_type
                current_type = metric_type
            continue

        # 跳过其他注释（HELP 等）
        if line.startswith('#'):
            continue

        try:
            # 解析 Prometheus 格式
            # 格式: metric_name{labels} value timestamp
            if '{' in line:
                # 有 labels
                metric_name = line[:line.index('{')]
                rest = line[line.index('{') + 1:]
                labels_part = rest[:rest.index('}')]
                value_part = rest[rest.index('}') + 1:].strip()
            else:
                # 无 labels
                parts = line.split()
                if len(parts) < 2:
                    continue
                metric_name = parts[0]
                labels_part = ""
                value_part = ' '.join(parts[1:])

            # 解析 value 和 timestamp
            value_parts = value_part.split()
            if len(value_parts) >= 1:
                value_str = value_parts[0]
                timestamp_str = value_parts[1] if len(value_parts) > 1 else ""
            else:
                continue

            # 跳过特殊值（NaN, Inf）
            if value_str in ['NaN', 'Inf', '+Inf', '-Inf']:
                logger.debug(
                    f"[NATS Helper] Skipping special value: {value_str}")
                continue

            # 创建 Point 对象
            point = Point(metric_name)

            # 先收集所有标签（优先级：common_tags > Prometheus labels）
            all_tags = {}

            # 1. 先添加 Prometheus labels（低优先级）
            if labels_part:
                # 使用正则匹配：key="value" 格式（支持值中包含逗号等特殊字符）
                label_pattern = r'(\w+)="([^"]*?)"'
                matches = re.findall(label_pattern, labels_part)

                for key, val in matches:
                    # 清理标签值中的换行符（Prometheus 可能包含 \n）
                    cleaned_val = val.replace(
                        '\\n', ' ').replace('  ', ' ').strip()
                    all_tags[key] = cleaned_val

            # 2. 再覆盖 common_tags（高优先级，已清理特殊字符）
            for tag_key, tag_value in common_tags.items():
                if tag_value:  # 跳过空值
                    all_tags[tag_key] = tag_value

            # 3. 添加到 Point 对象
            for tag_key, tag_value in all_tags.items():
                point.tag(tag_key, tag_value)

            # 确定 field 名称（从 TYPE 注释中提取）
            field_name = metric_types.get(
                metric_name, current_type if current_type else "value")

            # 添加 field（Point 会自动处理类型：int -> i 后缀，float 保持原样，str 加引号）
            try:
                if '.' in value_str or 'e' in value_str.lower():
                    # 浮点数
                    point.field(field_name, float(value_str))
                else:
                    # 整数
                    point.field(field_name, int(value_str))
            except ValueError:
                # 字符串值
                point.field(field_name, value_str)

            # 转换时间戳：统一转换为纳秒（InfluxDB 默认精度）
            if timestamp_str:
                try:
                    ts = int(timestamp_str)
                    if len(timestamp_str) == 13:
                        # 毫秒 -> 纳秒
                        ts_ns = ts * 1000000
                    elif len(timestamp_str) == 10:
                        # 秒 -> 纳秒
                        ts_ns = ts * 1000000000
                    elif len(timestamp_str) == 19:
                        # 已经是纳秒
                        ts_ns = ts
                    else:
                        # 其他长度的时间戳，尝试标准化
                        if ts > 9999999999999:  # 大于13位
                            ts_ns = int(str(ts)[:19].ljust(19, '0'))
                        else:
                            ts_ns = ts * 1000000

                    point.time(ts_ns, WritePrecision.NS)
                except ValueError:
                    logger.warning(
                        f"[NATS Helper] Invalid timestamp: {timestamp_str}")

            # 生成 Line Protocol（Point 自动处理转义和格式化）
            line_protocol = point.to_line_protocol()
            lines.append(line_protocol)

        except Exception as e:
            logger.debug(
                f"[NATS Helper] Failed to parse line: {line[:100]}, error: {e}")
            continue

    return lines


def _build_common_tags(params: Dict[str, Any]) -> Dict[str, str]:
    """
    构建通用的 tags（从 API 传递的参数中获取）

    优先使用 params['tags'] 中传递的标签，
    如果没有则使用默认值

    核心 Tags（5个）：
    - agent_id: 采集代理标识
    - instance_id: 实例标识
    - instance_type: 实例类型
    - collect_type: 采集类型
    - config_type: 配置类型

    Args:
        params: 采集参数

    Returns:
        tags 字典
    """
    # 从 API 传递的 tags
    api_tags = params.get('tags', {})

    # 获取基础参数用于生成默认值
    host = params.get('host', params.get('node_id', 'unknown'))
    monitor_type = params.get(
        'monitor_type', params.get('plugin_name', 'unknown'))

    # 构建 tags：优先使用用户传递的值，没有的用默认值
    tags = {
        'agent_id': api_tags.get('agent_id') or f"stargazer-{host}",
        'instance_id': api_tags.get('instance_id') or host,
        'instance_type': api_tags.get('instance_type') or monitor_type,
        'collect_type': api_tags.get('collect_type') or 'monitor',
        'config_type': api_tags.get('config_type') or 'auto',
    }

    # 清理 tags 中的特殊字符
    cleaned_tags = {}
    for k, v in tags.items():
        if v:  # 只保留非空值
            # InfluxDB tags 不能包含空格、逗号、等号
            cleaned_value = str(v).replace(
                ' ', '_').replace(',', '_').replace('=', '_')
            cleaned_tags[k] = cleaned_value

    return cleaned_tags