# -- coding: utf-8 --
# @File: nats_helper.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
NATS 推送辅助工具
处理指标数据推送到 NATS（InfluxDB Line Protocol 格式）
"""

import asyncio
import hashlib
import json
import os
import time
from collections import deque
from typing import Any, Dict, Iterable, Iterator

from core.collection.contracts import StructuredMetricsPayload
from core.infra.nats_utils import NatsLinesPublishError, nats_publish, nats_publish_lines
from influxdb_client import Point, WritePrecision
from sanic.log import logger

MAX_NATS_LINES_PER_FLUSH = 1000
MAX_NATS_BYTES_PER_FLUSH = 900_000
MAX_NATS_LINE_BYTES = 900_000
MAX_NATS_LINES_PER_RESULT = 100_000
MAX_NATS_BYTES_PER_RESULT = 64 * 1024 * 1024


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
        attempted_count: int | None = None,
        attempted_indices: tuple[int, ...] = (),
        confirmed_indices: tuple[int, ...] = (),
    ):
        self.task_id = task_id
        self.subject = subject
        self.total_lines = total_lines
        self.success_count = success_count
        self.delivery_detected = delivery_detected
        self.attempts = attempts
        self.reason = reason
        self.attempted_count = success_count if attempted_count is None else int(attempted_count)
        self.attempted_indices = attempted_indices
        self.confirmed_indices = confirmed_indices
        super().__init__(
            f"metrics publish incomplete: task_id={task_id}, subject={subject}, "
            f"success={success_count}/{total_lines}, delivery_detected={delivery_detected}, "
            f"attempts={attempts}, reason={reason}"
        )


def _has_confirmed_delivery(delivered_count: int) -> bool:
    return delivered_count > 0


async def _publish_lines_with_retry(
    subject: str,
    influx_lines: list[str],
    task_id: str,
    *,
    before_publish=None,
    message_ids=None,
) -> int:
    """执行一次 NATS 发布；重试由目标执行器统一管理。"""
    total_lines = len(influx_lines)
    try:
        publish_kwargs = {}
        if before_publish is not None:
            publish_kwargs["before_publish"] = before_publish
        if message_ids is not None:
            publish_kwargs["message_ids"] = message_ids
        success_count = await nats_publish_lines(subject, influx_lines, **publish_kwargs)
    except NatsLinesPublishError as error:
        raise MetricsPublishError(
            task_id=task_id,
            subject=subject,
            total_lines=total_lines,
            success_count=len(error.confirmed_indices),
            delivery_detected=bool(error.delivery_detected),
            attempts=1,
            reason=type(error.error).__name__,
            attempted_count=error.attempted_count_before_failure,
            attempted_indices=tuple(getattr(error, "attempted_indices", ())),
            confirmed_indices=tuple(getattr(error, "confirmed_indices", ())),
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
            attempted_count=total_lines,
        ) from error

    skipped_count = len(getattr(before_publish, "skipped_indices", ()))
    expected_count = total_lines - skipped_count
    if success_count == expected_count:
        logger.info(
            "event=nats_metrics_publish_succeeded task_id=%s subject=%s "
            "success_count=%s total_lines=%s skipped_count=%s | "
            "NATS指标推送成功 成功行数=%s/%s 跳过行数=%s",
            task_id,
            subject,
            success_count,
            total_lines,
            skipped_count,
            success_count,
            total_lines,
            skipped_count,
        )
        return success_count
    raise MetricsPublishError(
        task_id=task_id,
        subject=subject,
        total_lines=total_lines,
        success_count=success_count,
        delivery_detected=_has_confirmed_delivery(success_count),
        attempts=1,
        reason=f"publish incomplete ({success_count}/{total_lines})",
        attempted_count=success_count,
    )


class PublishCancelledBeforeDeliveryError(RuntimeError):
    delivery_detected = False


class MetricResultTooLargeError(ValueError):
    error_code = "result_too_large"


class MetricFormatError(ValueError):
    error_code = "metric_format_invalid"


class _DeliveryAttemptFilter:
    def __init__(self, line_result_ids, attempt_states) -> None:
        self._line_result_ids = line_result_ids
        self._attempt_states = attempt_states
        self.skipped_indices: set[int] = set()
        self.cancelled_result_ids: set[str] = set()

    def __call__(self, index: int) -> bool:
        result_id = self._line_result_ids[index]
        state = self._attempt_states.get(result_id)
        if state is None or state.mark_delivery_started():
            return True
        self.skipped_indices.add(index)
        self.cancelled_result_ids.add(result_id)
        return False


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
        logger.debug(f"[NATS Helper] Published callback to {subject} for task {task_id}")
    except Exception as err:
        logger.exception(
            "event=callback_publish_failed task_id=%s subject=%s " "failed_stage=callback_publish error_type=%s",
            task_id,
            subject,
            type(err).__name__,
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
        logger.debug(f"[NATS Helper] Published credential result to {subject} for task {task_id}")
    except Exception as err:
        logger.exception(
            "event=credential_result_publish_failed task_id=%s subject=%s " "failed_stage=credential_result_publish error_type=%s",
            task_id,
            subject,
            type(err).__name__,
        )
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

    # 直接回调路径也先完整校验，避免后续非法行导致单目标部分投递。
    await asyncio.to_thread(_validate_metric_result, metrics_data, params)

    # 将 Prometheus 格式转换为 InfluxDB Line Protocol 格式
    success_count = 0
    line_ordinal = 0
    result_id = str(params.get("collection_result_id") or task_id)
    chunks = iter(_iter_line_chunks(_iter_metrics_to_influx(metrics_data, params)))
    while chunk := await asyncio.to_thread(next, chunks, None):
        message_ids = tuple(_metric_message_id(result_id, line_ordinal + index, line) for index, line in enumerate(chunk))
        publish_kwargs = {"message_ids": message_ids} if _metrics_jetstream_enabled() else {}
        success_count += await _publish_lines_with_retry(
            subject,
            chunk,
            task_id,
            **publish_kwargs,
        )
        line_ordinal += len(chunk)
    logger.info(f"[NATS Helper] Successfully published {success_count} metrics " f"to '{subject}' for task {task_id}")
    return success_count


async def publish_metrics_batch_to_nats(entries, *, metrics=None) -> dict[str, BaseException | None]:
    """按 (task_id, subject) 公平轮转微批，并逐目标返回结果。"""
    outcomes: dict[str, BaseException | None] = {}
    metric_topic_prefix = os.getenv("NATS_METRIC_TOPIC", "metrics")
    lane_entries: dict[tuple[str, str], list[tuple[Any, Dict[str, Any], str, str]]] = {}
    for index, (_ctx, metrics_data, params, task_id) in enumerate(entries):
        result_id = str(params.get("collection_result_id") or f"{task_id}:legacy:{index}")
        outcomes[result_id] = None
        task_type = params.get("monitor_type") or params.get("plugin_name", params.get("model_id", "unknown"))
        subject = f"{metric_topic_prefix}.{task_type}"
        lane_entries.setdefault((str(task_id), subject), []).append((metrics_data, params, str(task_id), result_id))

    lanes = deque(
        _SubjectPublishLane(subject, grouped_entries, outcomes, metrics=metrics) for (_task_id, subject), grouped_entries in lane_entries.items()
    )
    while lanes:
        lane = lanes.popleft()
        if await lane.publish_round():
            lanes.append(lane)
    return outcomes


class _SubjectPublishLane:
    """一个 task/subject lane；每轮每个目标最多发送一个 chunk。"""

    def __init__(self, subject, entries, outcomes, *, metrics=None) -> None:
        self.subject = subject
        self.outcomes = outcomes
        self.metrics = metrics
        self.delivered_result_ids: set[str] = set()
        self.failed_result_ids: set[str] = set()
        self.attempt_states = {
            result_id: params.get("_publish_attempt_state")
            for _metrics_data, params, _task_id, result_id in entries
            if params.get("_publish_attempt_state") is not None
        }
        self.states = deque(
            {
                "chunks": None,
                "metrics_data": metrics_data,
                "params": params,
                "task_id": task_id,
                "result_id": result_id,
                "validated": False,
                "line_count": 0,
                "byte_count": 0,
            }
            for metrics_data, params, task_id, result_id in entries
        )

    @staticmethod
    def _next_state_chunk(state):
        if not state["validated"]:
            _validate_metric_result(state["metrics_data"], state["params"])
            state["validated"] = True
        if state["chunks"] is None:
            state["chunks"] = iter(_iter_line_chunks(_iter_metrics_to_influx(state["metrics_data"], state["params"])))
        return next(state["chunks"], None)

    async def publish_round(self) -> bool:
        selected = [self.states.popleft() for _ in range(min(50, len(self.states)))]
        buffered_lines: list[str] = []
        buffered_result_ids: list[str] = []
        buffered_message_ids: list[str] = []
        buffered_bytes = 0
        buffered_task_id = ""
        continuing_states = []

        async def flush_buffer() -> None:
            nonlocal buffered_lines, buffered_result_ids, buffered_message_ids, buffered_bytes, buffered_task_id
            if not buffered_lines:
                return
            lines = buffered_lines
            line_result_ids = tuple(buffered_result_ids)
            message_ids = tuple(buffered_message_ids)
            result_ids = tuple(dict.fromkeys(line_result_ids))
            task_id = buffered_task_id
            buffered_lines = []
            buffered_result_ids = []
            buffered_message_ids = []
            buffered_bytes = 0
            buffered_task_id = ""
            attempt_filter = _DeliveryAttemptFilter(line_result_ids, self.attempt_states)
            publish_kwargs = {}
            if _metrics_jetstream_enabled():
                publish_kwargs["message_ids"] = message_ids
            try:
                if self.attempt_states:
                    await _publish_lines_with_retry(
                        self.subject,
                        lines,
                        task_id,
                        before_publish=attempt_filter,
                        **publish_kwargs,
                    )
                else:
                    await _publish_lines_with_retry(
                        self.subject,
                        lines,
                        task_id,
                        **publish_kwargs,
                    )
            except Exception as error:  # noqa: BLE001 - 仅归因当前有界 chunk
                attempted_indices = tuple(getattr(error, "attempted_indices", ()))
                confirmed_indices = tuple(getattr(error, "confirmed_indices", ()))
                attempted_count = max(0, min(len(lines), int(getattr(error, "attempted_count", 0))))
                if self.metrics is not None:
                    metric_name = "publish_flush_failure_total" if attempted_count else "publish_connect_failure_total"
                    self.metrics.increment(metric_name)
                    reason = str(getattr(error, "reason", type(error).__name__)).lower()
                    if "timeout" in reason:
                        self.metrics.increment("publish_delivery_timeout_total")
                attempted_index_set = set(attempted_indices)
                confirmed_index_set = set(confirmed_indices)
                if not attempted_index_set and attempted_count:
                    attempted_index_set.update(range(attempted_count))
                if self.metrics is not None and confirmed_index_set:
                    confirmed_bytes = sum(len(lines[index].encode("utf-8")) for index in confirmed_index_set)
                    confirmed_result_ids = {line_result_ids[index] for index in confirmed_index_set}
                    self.metrics.increment("publish_lines_total", len(confirmed_index_set))
                    self.metrics.increment("publish_bytes_total", confirmed_bytes)
                    self.metrics.observe("publish_chunk_lines", len(confirmed_index_set))
                    self.metrics.observe("publish_chunk_bytes", confirmed_bytes)
                    self.metrics.observe("publish_targets_per_chunk", len(confirmed_result_ids))
                for result_id in result_ids:
                    if result_id in attempt_filter.cancelled_result_ids:
                        self.outcomes[result_id] = PublishCancelledBeforeDeliveryError("publish cancelled before NATS delivery")
                        self.failed_result_ids.add(result_id)
                        continue
                    result_line_indices = tuple(index for index, owner in enumerate(line_result_ids) if owner == result_id)
                    result_confirmed_indices = tuple(index for index in result_line_indices if index in confirmed_index_set)
                    if result_line_indices and len(result_confirmed_indices) == len(result_line_indices):
                        self.delivered_result_ids.add(result_id)
                        continue
                    result_attempted_indices = tuple(index for index in result_line_indices if index in attempted_index_set)
                    delivery_detected = result_id in self.delivered_result_ids or bool(result_attempted_indices)
                    self.outcomes[result_id] = MetricsPublishError(
                        task_id=task_id,
                        subject=self.subject,
                        total_lines=len(result_line_indices),
                        success_count=len(result_confirmed_indices),
                        delivery_detected=delivery_detected,
                        attempts=1,
                        reason=type(error).__name__,
                        attempted_count=len(result_attempted_indices),
                        attempted_indices=result_attempted_indices,
                        confirmed_indices=result_confirmed_indices,
                    )
                    self.failed_result_ids.add(result_id)
                return
            for result_id in attempt_filter.cancelled_result_ids:
                self.outcomes[result_id] = PublishCancelledBeforeDeliveryError("publish cancelled before NATS delivery")
                self.failed_result_ids.add(result_id)
            delivered_ids = tuple(result_id for result_id in result_ids if result_id not in attempt_filter.cancelled_result_ids)
            self.delivered_result_ids.update(delivered_ids)
            if self.metrics is not None:
                delivered_line_indices = set(range(len(lines))) - attempt_filter.skipped_indices
                delivered_bytes = sum(len(lines[index].encode("utf-8")) for index in delivered_line_indices)
                self.metrics.increment("publish_lines_total", len(delivered_line_indices))
                self.metrics.increment("publish_bytes_total", delivered_bytes)
                self.metrics.observe("publish_chunk_lines", len(delivered_line_indices))
                self.metrics.observe("publish_chunk_bytes", delivered_bytes)
                self.metrics.observe("publish_targets_per_chunk", len(delivered_ids))

        for offset in range(0, len(selected), 4):
            group = selected[offset : offset + 4]
            started = time.monotonic()
            chunks = await asyncio.gather(
                *(asyncio.to_thread(self._next_state_chunk, state) for state in group),
                return_exceptions=True,
            )
            if self.metrics is not None:
                self.metrics.observe("publish_encode_duration_seconds", time.monotonic() - started)
            for state, chunk in zip(group, chunks):
                task_id = state["task_id"]
                result_id = state["result_id"]
                error = chunk if isinstance(chunk, BaseException) else None
                if error is not None:
                    self.outcomes[result_id] = error
                    self.failed_result_ids.add(result_id)
                    continue
                if chunk is None:
                    continue
                chunk_bytes = sum(len(line.encode("utf-8")) for line in chunk)
                first_line_ordinal = state["line_count"]
                state["line_count"] += len(chunk)
                state["byte_count"] += chunk_bytes
                if buffered_lines and (
                    len(buffered_lines) + len(chunk) > MAX_NATS_LINES_PER_FLUSH or buffered_bytes + chunk_bytes > MAX_NATS_BYTES_PER_FLUSH
                ):
                    await flush_buffer()
                if result_id in self.failed_result_ids:
                    continue
                if not buffered_lines:
                    buffered_task_id = task_id
                buffered_lines.extend(chunk)
                buffered_result_ids.extend([result_id] * len(chunk))
                buffered_message_ids.extend(_metric_message_id(result_id, first_line_ordinal + index, line) for index, line in enumerate(chunk))
                buffered_bytes += chunk_bytes
                if len(buffered_lines) >= MAX_NATS_LINES_PER_FLUSH or buffered_bytes >= MAX_NATS_BYTES_PER_FLUSH:
                    await flush_buffer()
                continuing_states.append(state)
        await flush_buffer()
        self.states.extend(state for state in continuing_states if state["result_id"] not in self.failed_result_ids)
        return bool(self.states)


def _metrics_jetstream_enabled() -> bool:
    return str(os.getenv("NATS_METRICS_JETSTREAM_ENABLED", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _metric_message_id(result_id: str, line_ordinal: int, line: str) -> str:
    digest = hashlib.sha256()
    digest.update(result_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(line_ordinal).encode("ascii"))
    digest.update(b"\0")
    digest.update(hashlib.sha256(line.encode("utf-8")).digest())
    return digest.hexdigest()


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
            raise MetricResultTooLargeError("metric line exceeds NATS payload limit")
        if chunk and (len(chunk) >= max_lines or chunk_bytes + line_bytes > max_bytes):
            yield chunk
            chunk = []
            chunk_bytes = 0
        chunk.append(line)
        chunk_bytes += line_bytes
    if chunk:
        yield chunk


def _validate_metric_result(metrics_data, params: Dict[str, Any]) -> None:
    """发送前完整扫描一次结果，保证单目标超限不会产生部分投递。"""
    line_count = 0
    byte_count = 0
    for line in _iter_metrics_to_influx(metrics_data, params):
        line_bytes = len(line.encode("utf-8"))
        if line_bytes > MAX_NATS_LINE_BYTES:
            raise ValueError("metric line exceeds NATS payload limit")
        line_count += 1
        byte_count += line_bytes
        if line_count > MAX_NATS_LINES_PER_RESULT:
            raise MetricResultTooLargeError("metric result exceeds line limit")
        if byte_count > MAX_NATS_BYTES_PER_RESULT:
            raise MetricResultTooLargeError("metric result exceeds byte limit")


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
    timestamp_ms = int(params.get("_publish_timestamp_ms") or time.time() * 1000)
    timestamp_ns = timestamp_ms * 1_000_000
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
        except MetricFormatError:
            raise
        except Exception as error:
            raise MetricFormatError(f"invalid Prometheus metric line: error_type={type(error).__name__}") from error
        if converted is not None:
            yield converted


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
            raise MetricFormatError("metric line must contain a name and value")
        metric_name = parts[0]
        labels_part = ""
        value_part = " ".join(parts[1:])

    if not metric_name.strip():
        raise MetricFormatError("metric name must not be empty")

    value_parts = value_part.split()
    if not value_parts:
        raise MetricFormatError("metric line must contain a value")
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
        point.field(
            field_name,
            float(value_str) if "." in value_str or "e" in value_str.lower() else int(value_str),
        )
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
        except ValueError as error:
            raise MetricFormatError("metric timestamp must be an integer") from error
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
            raise MetricFormatError("metric label must contain '='")

        idx += 1  # skip '='

        # Skip optional spaces before value
        while idx < length and label_str[idx].isspace():
            idx += 1

        if idx >= length or label_str[idx] != '"':
            raise MetricFormatError("metric label value must be quoted")

        idx += 1  # skip opening quote
        value_chars = []
        closing_quote_found = False

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
                closing_quote_found = True
                break
            value_chars.append(ch)
            idx += 1

        if not closing_quote_found:
            raise MetricFormatError("metric label value is missing a closing quote")
        labels[key] = "".join(value_chars)

        # Skip trailing whitespaces after value and optional comma
        while idx < length and label_str[idx].isspace():
            idx += 1
        if idx < length and label_str[idx] == ",":
            idx += 1
        elif idx < length:
            raise MetricFormatError("metric labels must be comma-separated")

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
        "collect_status",
    ):
        if params.get(identity_key) not in (None, ""):
            tags[identity_key] = params[identity_key]

    return {key: _clean_common_tag_value(value) for key, value in tags.items() if value}
