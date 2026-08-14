# -- coding: utf-8 --
# @File: nats_helper.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
NATS 推送辅助工具
处理指标数据推送到 NATS（InfluxDB Line Protocol 格式）
"""

import asyncio
import json
import os
import time
import traceback
from typing import Any, Dict, Iterable, Iterator

from core.collection.contracts import StructuredMetricsPayload
from core.infra.nats_utils import NatsLinesPublishError, nats_publish, nats_publish_lines
from influxdb_client import Point, WritePrecision
from sanic.log import logger

MAX_NATS_LINES_PER_FLUSH = 1000
MAX_NATS_BYTES_PER_FLUSH = 900_000
MAX_NATS_LINE_BYTES = 900_000


class MetricsPublishError(RuntimeError):
    def __init__(
        self,
        task_id: str,
        subject: str,
        total_lines: int,
        success_count: int,
        delivery_detected: bool,
        attempts: int,
        reason: str,
    ):
        self.task_id = task_id
        self.subject = subject
        self.total_lines = total_lines
        self.success_count = success_count
        self.delivery_detected = delivery_detected
        self.attempts = attempts
        self.reason = reason
        super().__init__(
            f"metrics publish incomplete: task_id={task_id}, subject={subject}, "
            f"success={success_count}/{total_lines}, delivery_detected={delivery_detected}, "
            f"attempts={attempts}, reason={reason}"
        )


def _has_confirmed_delivery(delivered_count: int) -> bool:
    return delivered_count > 0


async def _publish_lines_with_retry(subject: str, influx_lines: list[str], task_id: str) -> int:
    """执行一次 NATS 发布；重试由目标执行器统一管理。"""
    total_lines = len(influx_lines)
    try:
        success_count = await nats_publish_lines(subject, influx_lines)
    except NatsLinesPublishError as error:
        raise MetricsPublishError(
            task_id=task_id,
            subject=subject,
            total_lines=total_lines,
            success_count=0,
            delivery_detected=bool(error.delivery_detected),
            attempts=1,
            reason=type(error).__name__,
        ) from error
    except Exception as error:
        # 普通异常无法证明服务端未收到，按不确定投递处理，避免重复数据。
        raise MetricsPublishError(
            task_id=task_id,
            subject=subject,
            total_lines=total_lines,
            success_count=int(getattr(error, "success_count", 0)),
            delivery_detected=True,
            attempts=1,
            reason=type(error).__name__,
        ) from error

    logger.info(f"[NATS Helper] Metrics publish task_id={task_id} subject={subject} " f"success_count={success_count} total_lines={total_lines}")
    if success_count == total_lines:
        return success_count
    raise MetricsPublishError(
        task_id=task_id,
        subject=subject,
        total_lines=total_lines,
        success_count=success_count,
        delivery_detected=_has_confirmed_delivery(success_count),
        attempts=1,
        reason=f"publish incomplete ({success_count}/{total_lines})",
    )


async def publish_callback_to_nats(result: Dict[str, Any], params: Dict[str, Any], task_id: str):
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
        logger.error(f"[NATS Helper] Failed to publish callback for task {task_id}: {err}\n{traceback.format_exc()}")
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
        logger.error(f"[NATS Helper] Failed to publish credential result for task {task_id}: {err}\n{traceback.format_exc()}")
        raise


async def publish_metrics_to_nats(ctx: Dict, metrics_data: str, params: Dict[str, Any], task_id: str) -> int:
    """
    将采集结果推送到 NATS 的 metrics 主题

    推送格式：InfluxDB Line Protocol（与 Telegraf 保持一致）
    每条指标数据单独发送一次消息

    Args:
        ctx: 采集运行上下文
        metrics_data: Prometheus 格式的指标数据
        params: 采集参数（包含 tags）
        task_id: 任务ID
    """
    # 获取 NATS Metric Topic 前缀（从环境变量读取，默认为 metrics）
    metric_topic_prefix = os.getenv("NATS_METRIC_TOPIC", "metrics")

    # 获取任务类型（monitor_type 或 plugin_name）
    task_type = params.get("monitor_type") or params.get("plugin_name", params.get("model_id", "unknown"))

    # 构建 subject: {prefix}.{task_type}
    # 例如: metrics.vmware, metrics.mysql, metrics.host 等
    subject = f"{metric_topic_prefix}.{task_type}"

    # 将 Prometheus 格式转换为 InfluxDB Line Protocol 格式
    success_count = 0
    chunks = iter(_iter_line_chunks(_iter_metrics_to_influx(metrics_data, params)))
    while chunk := await asyncio.to_thread(next, chunks, None):
        success_count += await _publish_lines_with_retry(subject, chunk, task_id)
    logger.info(f"[NATS Helper] Successfully published {success_count} metrics " f"to '{subject}' for task {task_id}")
    return success_count


async def publish_metrics_batch_to_nats(entries, *, metrics=None) -> dict[str, BaseException | None]:
    """逐目标流式编码发布，并按 collection_result_id 返回独立结果。"""
    outcomes: dict[str, BaseException | None] = {}
    metric_topic_prefix = os.getenv("NATS_METRIC_TOPIC", "metrics")
    for index, (_ctx, metrics_data, params, task_id) in enumerate(entries):
        result_id = str(params.get("collection_result_id") or f"{task_id}:legacy:{index}")
        outcomes[result_id] = None
        task_type = params.get("monitor_type") or params.get("plugin_name", params.get("model_id", "unknown"))
        subject = f"{metric_topic_prefix}.{task_type}"
        delivered_lines = 0
        try:
            chunks = iter(_iter_line_chunks(_iter_metrics_to_influx(metrics_data, params)))
            while chunk := await asyncio.to_thread(next, chunks, None):
                delivered_lines += await _publish_lines_with_retry(subject, chunk, str(task_id))
                if metrics is not None:
                    metrics.increment("publish_lines_total", len(chunk))
                    metrics.increment("publish_bytes_total", sum(len(line.encode("utf-8")) for line in chunk))
        except Exception as error:  # noqa: BLE001 - 编码/传输失败只影响当前目标
            if delivered_lines and not bool(getattr(error, "delivery_detected", False)):
                error = MetricsPublishError(
                    task_id=str(task_id),
                    subject=subject,
                    total_lines=delivered_lines,
                    success_count=delivered_lines,
                    delivery_detected=True,
                    attempts=1,
                    reason=type(error).__name__,
                )
            outcomes[result_id] = error
    return outcomes


def _iter_line_chunks(
    lines: Iterable[str],
    *,
    max_lines: int | None = None,
    max_bytes: int | None = None,
):
    """按行数和 UTF-8 字节数生成有界 flush 批次。"""
    max_lines = MAX_NATS_LINES_PER_FLUSH if max_lines is None else max_lines
    max_bytes = MAX_NATS_BYTES_PER_FLUSH if max_bytes is None else max_bytes
    chunk: list[str] = []
    chunk_bytes = 0
    for line in lines:
        line_bytes = len(line.encode("utf-8"))
        if line_bytes > MAX_NATS_LINE_BYTES:
            raise ValueError("metric line exceeds NATS payload limit")
        if chunk and (len(chunk) >= max_lines or chunk_bytes + line_bytes > max_bytes):
            yield chunk
            chunk = []
            chunk_bytes = 0
        chunk.append(line)
        chunk_bytes += line_bytes
    if chunk:
        yield chunk


def _convert_metrics_to_influx(metrics_data, params: Dict[str, Any]) -> list[str]:
    return list(_iter_metrics_to_influx(metrics_data, params))


def _iter_metrics_to_influx(metrics_data, params: Dict[str, Any]) -> Iterator[str]:
    if isinstance(metrics_data, StructuredMetricsPayload):
        yield from _iter_structured_metrics_to_influx(metrics_data, params)
        return
    yield from _iter_prometheus_to_influx(str(metrics_data), params)


def convert_structured_metrics_to_influx(payload: StructuredMetricsPayload, params: Dict[str, Any]) -> list[str]:
    """把结构化配置采集结果直接编码为既有 Influx Line Protocol。"""
    return list(_iter_structured_metrics_to_influx(payload, params))


def _iter_structured_metrics_to_influx(payload: StructuredMetricsPayload, params: Dict[str, Any]) -> Iterator[str]:
    common_tags = _build_common_tags(params)
    timestamp_ns = int(time.time() * 1000) * 1_000_000
    for model_id, items in payload.data.items():
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            point = Point(f"{model_id}_info")
            labels = {
                str(key): str(value).replace("\r", " ").replace("\n", " ").strip()
                for key, value in item.items()
                if value and not isinstance(value, (list, dict))
            }
            labels["model_id"] = str(model_id)
            labels.update(common_tags)
            for key, value in labels.items():
                if value:
                    point.tag(key, value)
            point.field("gauge", 1)
            point.time(timestamp_ns, WritePrecision.NS)
            yield point.to_line_protocol()


def convert_prometheus_to_influx(prometheus_data: str, params: Dict[str, Any]) -> list:  # noqa: C901
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
    return list(_iter_prometheus_to_influx(prometheus_data, params))


def _iter_prometheus_to_influx(prometheus_data: str, params: Dict[str, Any]) -> Iterator[str]:  # noqa: C901
    if not prometheus_data or not prometheus_data.strip():
        return

    # 获取通用 tags（从 API 传递的参数，已清理特殊字符）
    common_tags = _build_common_tags(params)

    # 用于记录每个指标的类型（从 TYPE 注释中提取）
    metric_types = {}  # {metric_name: field_type}
    current_type = None

    for line in _iter_prometheus_logical_lines(prometheus_data):
        # 解析 TYPE 注释，提取指标类型
        if line.startswith("# TYPE "):
            parts = line.split()
            if len(parts) >= 4:
                metric_name = parts[2]
                metric_type = parts[3]
                metric_types[metric_name] = metric_type
                current_type = metric_type
            continue

        if line.startswith("#"):
            continue

        try:
            converted = _prometheus_line_to_influx(line, common_tags, metric_types, current_type)
            if converted is not None:
                yield converted
        except Exception as e:
            logger.debug(f"[NATS Helper] Failed to parse line: {line[:100]}, error: {e}")


def _iter_prometheus_logical_lines(prometheus_data: str) -> Iterator[str]:
    current_line = ""
    start = 0
    data_length = len(prometheus_data)
    while start <= data_length:
        end = prometheus_data.find("\n", start)
        if end < 0:
            end = data_length
        raw_line = prometheus_data[start:end]
        start = end + 1
        line = raw_line.strip()
        if not line:
            if end == data_length:
                break
            continue

        # 如果是注释行或新的指标行（不以 \ 开头），则保存之前的行
        if line.startswith("#") or (current_line and not line.startswith("\\")):
            if current_line:
                yield current_line
            current_line = line
        else:
            # 续行：拼接到当前行
            current_line = f"{current_line} {line}" if current_line else line
        if end == data_length:
            break

    if current_line:
        yield current_line


def _prometheus_line_to_influx(
    line: str,
    common_tags: Dict[str, str],
    metric_types: Dict[str, str],
    current_type: str | None,
) -> str | None:
    if "{" in line:
        metric_name = line[: line.index("{")]
        rest = line[line.index("{") + 1 :]
        labels_part = rest[: rest.rindex("}")]
        value_part = rest[rest.rindex("}") + 1 :].strip()
    else:
        parts = line.split()
        if len(parts) < 2:
            return None
        metric_name = parts[0]
        labels_part = ""
        value_part = " ".join(parts[1:])

    value_parts = value_part.split()
    if not value_parts:
        return None
    value_str = value_parts[0]
    timestamp_str = value_parts[1] if len(value_parts) > 1 else ""
    if value_str in ["NaN", "Inf", "+Inf", "-Inf"]:
        logger.debug(f"[NATS Helper] Skipping special value: {value_str}")
        return None

    point = Point(metric_name)
    all_tags = {}
    if labels_part:
        for key, raw_val in _parse_prometheus_labels(labels_part).items():
            all_tags[key] = _decode_prometheus_value(raw_val)
    for tag_key, tag_value in common_tags.items():
        if tag_value:
            all_tags[tag_key] = tag_value
    for tag_key, tag_value in all_tags.items():
        point.tag(tag_key, tag_value)

    field_name = metric_types.get(metric_name, current_type if current_type else "value")
    try:
        point.field(field_name, float(value_str) if "." in value_str or "e" in value_str.lower() else int(value_str))
    except ValueError:
        point.field(field_name, value_str)

    if timestamp_str:
        try:
            ts = int(timestamp_str)
            if len(timestamp_str) == 13:
                ts_ns = ts * 1000000
            elif len(timestamp_str) == 10:
                ts_ns = ts * 1000000000
            elif len(timestamp_str) == 19:
                ts_ns = ts
            elif ts > 9999999999999:
                ts_ns = int(str(ts)[:19].ljust(19, "0"))
            else:
                ts_ns = ts * 1000000
            point.time(ts_ns, WritePrecision.NS)
        except ValueError:
            logger.warning(f"[NATS Helper] Invalid timestamp: {timestamp_str}")
    return point.to_line_protocol()


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
            logger.debug(f"[NATS Helper] Incomplete label segment near key '{key}' in '{label_str}'")
            break

        idx += 1  # skip '='

        # Skip optional spaces before value
        while idx < length and label_str[idx].isspace():
            idx += 1

        if idx >= length or label_str[idx] != '"':
            logger.debug(f"[NATS Helper] Missing opening quote for key '{key}' in '{label_str}'")
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


def _clean_common_tag_value(value) -> str:
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ").split())


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
    for identity_key in (
        "collection_task_id",
        "collection_fence",
        "collection_target",
        "collection_plugin_ref",
        "collection_result_id",
    ):
        if params.get(identity_key) not in (None, ""):
            tags[identity_key] = params[identity_key]

    return {key: _clean_common_tag_value(value) for key, value in tags.items() if value}
