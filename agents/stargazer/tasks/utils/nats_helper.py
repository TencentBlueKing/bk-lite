# -- coding: utf-8 --
# @File: nats_helper.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
NATS 推送辅助工具
处理指标数据推送到 NATS（InfluxDB Line Protocol 格式）
"""

import json
import os
import asyncio
import traceback
from typing import Dict, Any
from sanic.log import logger
from influxdb_client import Point, WritePrecision
from core.nats_utils import nats_publish, nats_publish_lines


class MetricsPublishError(RuntimeError):
    def __init__(
        self,
        task_id: str,
        subject: str,
        total_lines: int,
        success_count: int,
        attempts: int,
        reason: str,
    ):
        self.task_id = task_id
        self.subject = subject
        self.total_lines = total_lines
        self.success_count = success_count
        self.attempts = attempts
        self.reason = reason
        super().__init__(
            f"metrics publish incomplete: task_id={task_id}, subject={subject}, "
            f"success={success_count}/{total_lines}, attempts={attempts}, reason={reason}"
        )


def _metrics_publish_retry_times() -> int:
    raw_value = os.getenv("NATS_METRICS_PUBLISH_RETRIES", "2")
    try:
        return max(int(raw_value), 0)
    except ValueError:
        return 2


async def _publish_lines_with_retry(subject: str, influx_lines: list[str], task_id: str) -> int:
    total_lines = len(influx_lines)
    max_retries = _metrics_publish_retry_times()
    last_error = ""
    success_count = 0

    for attempt in range(1, max_retries + 2):
        try:
            success_count = await nats_publish_lines(subject, influx_lines)
            if success_count == total_lines:
                return success_count
            last_error = f"publish incomplete ({success_count}/{total_lines})"
        except Exception as err:
            success_count = 0
            last_error = f"{type(err).__name__}: {err}"

        if attempt <= max_retries:
            await asyncio.sleep(min(attempt * 0.2, 1.0))

    raise MetricsPublishError(
        task_id=task_id,
        subject=subject,
        total_lines=total_lines,
        success_count=success_count,
        attempts=max_retries + 1,
        reason=last_error,
    )


async def publish_callback_to_nats(
    result: Dict[str, Any], params: Dict[str, Any], task_id: str
):
    callback_subject = params.get("callback_subject")
    if not callback_subject:
        logger.warning(f"[NATS Helper] callback_subject missing for task {task_id}")
        return

    callback_data = dict(result or {})
    if callback_data.get("collect_task_id") in (None, ""):
        callback_data["collect_task_id"] = params.get("collect_task_id")
    nats_namespace = os.getenv("NATS_NAMESPACE", "bklite")
    subject = f"{nats_namespace}.{callback_subject}"

    # server 端 NATS handler 按 {"args": [], "kwargs": {}} 格式分发参数
    payload = {"args": [], "kwargs": {"data": callback_data}}

    try:
        await nats_publish(subject, payload)
        logger.info(f"[NATS Helper] Published callback to {subject} for task {task_id}")
    except Exception as err:
        logger.error(
            f"[NATS Helper] Failed to publish callback for task {task_id}: {err}\n{traceback.format_exc()}"
        )
        raise


async def publish_credential_result_to_nats(result: Dict[str, Any], params: Dict[str, Any], task_id: str):
    callback_subject = params.get("credential_result_subject")
    if not callback_subject:
        return

    nats_namespace = os.getenv("NATS_NAMESPACE", "bklite")
    subject = f"{nats_namespace}.{callback_subject}"
    payload = {"args": [], "kwargs": {"data": dict(result or {})}}
    try:
        await nats_publish(subject, payload)
        logger.info(f"[NATS Helper] Published credential result to {subject} for task {task_id}")
    except Exception as err:
        logger.error(
            f"[NATS Helper] Failed to publish credential result for task {task_id}: {err}\n{traceback.format_exc()}"
        )
        raise


async def publish_metrics_to_nats(
    ctx: Dict, metrics_data: str, params: Dict[str, Any], task_id: str
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
    # 获取 NATS Metric Topic 前缀（从环境变量读取，默认为 metrics）
    metric_topic_prefix = os.getenv("NATS_METRIC_TOPIC", "metrics")

    # 获取任务类型（monitor_type 或 plugin_name）
    task_type = params.get("monitor_type") or params.get(
        "plugin_name", params.get("model_id", "unknown")
    )

    # 构建 subject: {prefix}.{task_type}
    # 例如: metrics.vmware, metrics.mysql, metrics.host 等
    subject = f"{metric_topic_prefix}.{task_type}"

    # 将 Prometheus 格式转换为 InfluxDB Line Protocol 格式
    influx_lines = convert_prometheus_to_influx(metrics_data, params)

    if not influx_lines:
        return

    # 复用进程级共享长连接逐行发送（与 Telegraf 保持一致）
    # 不再每次采集都新建 TLS 连接，避免事件循环繁忙时握手超时被 reset
    await _publish_lines_with_retry(subject, influx_lines, task_id)


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
    for line in prometheus_data.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 如果是注释行或新的指标行（不以 \ 开头），则保存之前的行
        if line.startswith("#") or (current_line and not line.startswith("\\")):
            if current_line:
                prometheus_lines.append(current_line)
            current_line = line
        else:
            # 续行：拼接到当前行
            current_line += " " + line

    # 添加最后一行
    if current_line:
        prometheus_lines.append(current_line)

    for line in prometheus_lines:
        # 解析 TYPE 注释，提取指标类型
        if line.startswith("# TYPE "):
            # 格式: # TYPE metric_name gauge|counter|histogram|summary
            parts = line.split()
            if len(parts) >= 4:
                metric_name = parts[2]
                metric_type = parts[3]  # gauge, counter, histogram, summary 等
                metric_types[metric_name] = metric_type
                current_type = metric_type
            continue

        # 跳过其他注释（HELP 等）
        if line.startswith("#"):
            continue

        try:
            # 解析 Prometheus 格式
            # 格式: metric_name{labels} value timestamp
            if "{" in line:
                # 有 labels
                metric_name = line[: line.index("{")]
                rest = line[line.index("{") + 1 :]
                labels_part = rest[: rest.rindex("}")]
                value_part = rest[rest.rindex("}") + 1 :].strip()
            else:
                # 无 labels
                parts = line.split()
                if len(parts) < 2:
                    continue
                metric_name = parts[0]
                labels_part = ""
                value_part = " ".join(parts[1:])

            # 解析 value 和 timestamp
            value_parts = value_part.split()
            if len(value_parts) >= 1:
                value_str = value_parts[0]
                timestamp_str = value_parts[1] if len(value_parts) > 1 else ""
            else:
                continue

            # 跳过特殊值（NaN, Inf）
            if value_str in ["NaN", "Inf", "+Inf", "-Inf"]:
                logger.debug(f"[NATS Helper] Skipping special value: {value_str}")
                continue

            # 创建 Point 对象
            point = Point(metric_name)

            # 先收集所有标签（优先级：common_tags > Prometheus labels）
            all_tags = {}

            # 1. 先添加 Prometheus labels（低优先级）
            if labels_part:
                parsed_labels = _parse_prometheus_labels(labels_part)

                for key, raw_val in parsed_labels.items():
                    cleaned_val = _decode_prometheus_value(raw_val)
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
                metric_name, current_type if current_type else "value"
            )

            # 添加 field（Point 会自动处理类型：int -> i 后缀，float 保持原样，str 加引号）
            try:
                if "." in value_str or "e" in value_str.lower():
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
                            ts_ns = int(str(ts)[:19].ljust(19, "0"))
                        else:
                            ts_ns = ts * 1000000

                    point.time(ts_ns, WritePrecision.NS)
                except ValueError:
                    logger.warning(f"[NATS Helper] Invalid timestamp: {timestamp_str}")

            # 生成 Line Protocol（Point 自动处理转义和格式化）
            line_protocol = point.to_line_protocol()
            lines.append(line_protocol)

        except Exception as e:
            logger.debug(
                f"[NATS Helper] Failed to parse line: {line[:100]}, error: {e}"
            )
            continue

    return lines


def _parse_prometheus_labels(label_str: str) -> Dict[str, str]:
    """Parse the label segment inside metric_name{...}."""
    labels = {}
    if not label_str:
        return labels

    length = len(label_str)
    idx = 0

    while idx < length:
        # Skip commas or spaces between pairs
        while idx < length and label_str[idx] in {",", " ", "\t"}:
            idx += 1

        if idx >= length:
            break

        key_start = idx
        while idx < length and label_str[idx] not in {"=", " ", "\t"}:
            idx += 1
        key = label_str[key_start:idx].strip()

        if not key:
            break

        # Move to '='
        while idx < length and label_str[idx] != "=":
            idx += 1

        if idx >= length or label_str[idx] != "=":
            logger.debug(
                f"[NATS Helper] Incomplete label segment near key '{key}' in '{label_str}'"
            )
            break

        idx += 1  # skip '='

        # Skip optional spaces before value
        while idx < length and label_str[idx].isspace():
            idx += 1

        if idx >= length or label_str[idx] != '"':
            logger.debug(
                f"[NATS Helper] Missing opening quote for key '{key}' in '{label_str}'"
            )
            break

        idx += 1  # skip opening quote
        value_chars = []

        while idx < length:
            ch = label_str[idx]
            if ch == "\\":
                # Preserve escape sequence to let decoder handle it later
                if idx + 1 < length:
                    value_chars.append(ch)
                    value_chars.append(label_str[idx + 1])
                    idx += 2
                    continue
                value_chars.append(ch)
                idx += 1
                break
            if ch == '"':
                idx += 1
                break
            value_chars.append(ch)
            idx += 1

        labels[key] = "".join(value_chars)

        # Skip trailing whitespaces after value and optional comma
        while idx < length and label_str[idx].isspace():
            idx += 1
        if idx < length and label_str[idx] == ",":
            idx += 1

    return labels


def _decode_prometheus_value(raw_value: str) -> str:
    """Convert Prometheus label raw value into decoded text."""
    if raw_value is None:
        return ""

    try:
        decoded = json.loads(f'"{raw_value}"')
    except json.JSONDecodeError:
        cleaned = raw_value.replace("\\n", " ").replace("  ", " ").strip()
        return cleaned

    return decoded.replace("\n", " ").strip()


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
    api_tags = params.get("tags", {})

    # 获取基础参数用于生成默认值
    host = params.get("host", params.get("node_id", "unknown"))
    monitor_type = params.get("monitor_type", params.get("plugin_name", "unknown"))

    # 构建 tags：优先使用用户传递的值，没有的用默认值
    tags = {
        "agent_id": api_tags.get("agent_id") or f"stargazer-{host}",
        "instance_id": api_tags.get("instance_id") or host,
        "instance_type": api_tags.get("instance_type") or monitor_type,
        "collect_type": api_tags.get("collect_type") or "monitor",
        "config_type": api_tags.get("config_type") or "auto",
    }

    # 清理 tags 中的特殊字符
    cleaned_tags = {}
    for k, v in tags.items():
        if v:  # 只保留非空值
            # InfluxDB tags 不能包含空格、逗号、等号
            cleaned_value = str(v).replace(" ", "_").replace(",", "_").replace("=", "_")
            cleaned_tags[k] = cleaned_value

    return cleaned_tags
