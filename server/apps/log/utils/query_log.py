import asyncio
import json
import re
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from decimal import Decimal, InvalidOperation
from json import JSONDecodeError
from typing import AsyncIterator

import requests
import requests.adapters
from requests.auth import HTTPBasicAuth

from apps.core.logger import log_logger as logger
from apps.log.constants.victoriametrics import VictoriaLogsConstants


class VictoriaMetricsAPI:
    REQUEST_TIMEOUT = 10

    def __init__(self):
        self.host = VictoriaLogsConstants.HOST
        self.username = VictoriaLogsConstants.USER or ""
        self.password = VictoriaLogsConstants.PWD or ""
        self.ssl_verify = VictoriaLogsConstants.SSL_VERIFY
        self.auth = self._build_auth()

    def _build_auth(self):
        if not self.username and not self.password:
            return None
        return HTTPBasicAuth(self.username, self.password)

    @staticmethod
    def _normalize_logsql_query(query: str) -> str:
        normalized = "" if query is None else str(query).strip()
        if not normalized:
            return normalized

        current = normalized
        for _ in range(2):
            try:
                decoded = json.loads(current)
            except (TypeError, ValueError, JSONDecodeError):
                break

            if not isinstance(decoded, str):
                break

            decoded = decoded.strip()
            if not decoded or decoded == current:
                current = decoded
                break

            current = decoded
        return current

    @staticmethod
    def _build_url(host: str, path: str) -> str:
        normalized_host = (host or "").rstrip("/")
        if not normalized_host:
            raise ValueError("VictoriaLogs host is not configured")
        return f"{normalized_host}{path}"

    @staticmethod
    def _extract_metric_value(metrics_text: str, metric_name: str, metric_type: str) -> int:
        sample_pattern = re.compile(
            r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+"
            r"(?P<value>[^\s]+)(?:\s+(?P<timestamp>[^\s]+))?$"
        )
        label_pattern = re.compile(r'(\w+)="((?:\\.|[^"])*)"')

        for raw_line in metrics_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            matched = sample_pattern.match(line)
            if not matched or matched.group("name") != metric_name:
                continue

            labels_str = matched.group("labels") or ""
            labels = {key: value.replace(r"\"", '"').replace(r"\\", "\\") for key, value in label_pattern.findall(labels_str)}
            if labels.get("type") != metric_type:
                continue

            value = matched.group("value")

            try:
                decimal_value = Decimal(value)
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"指标 {metric_name}[type={metric_type}] 的值非法: {value}") from exc

            if decimal_value != decimal_value.to_integral_value():
                raise ValueError(f"指标 {metric_name}[type={metric_type}] 的值不是整数: {value}")

            return int(decimal_value)

        raise ValueError(f"未找到指标 {metric_name}[type={metric_type}]")

    def all_field_names(self, query, start, end):
        query = self._normalize_logsql_query(query)
        logger.info(
            "发送VictoriaLogs field_names查询",
            extra={"query": query or "*", "start": start, "end": end},
        )
        data = {
            "query": query or "*",
            "start": start,
            "end": end,
            "ignore_pipes": 1,
        }
        response = requests.get(
            self._build_url(self.host, "/select/logsql/field_names"),
            params=data,
            auth=self.auth,
            verify=self.ssl_verify,
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def field_values(self, start, end, field, limit=100, query=None):
        limit = VictoriaLogsConstants.normalize_field_values_limit(limit, default=100, clamp=True)
        query = self._normalize_logsql_query(query)
        logger.info(
            "发送VictoriaLogs field_values查询",
            extra={"query": query or f"{field}:*", "field": field, "start": start, "end": end, "limit": limit},
        )
        data = {
            "query": query or f"{field}:*",
            "field": field,
            "start": start,
            "end": end,
            "limit": limit,
        }
        response = requests.get(
            self._build_url(self.host, "/select/logsql/field_values"),
            params=data,
            auth=self.auth,
            verify=self.ssl_verify,
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def query(self, query, start, end, limit=10):
        limit = VictoriaLogsConstants.normalize_query_limit(limit, default=10, clamp=True)
        query = self._normalize_logsql_query(query)
        logger.info(
            "发送VictoriaLogs query查询",
            extra={"query": query, "start": start, "end": end, "limit": limit},
        )
        data = {"query": query, "start": start, "end": end, "limit": limit}
        response = requests.post(
            self._build_url(self.host, "/select/logsql/query"),
            params=data,
            auth=self.auth,
            verify=self.ssl_verify,
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = []
        skipped_lines = 0

        for line_number, line in enumerate(response.iter_lines(decode_unicode=True), start=1):
            if not line:
                continue

            try:
                result.append(json.loads(line))
            except JSONDecodeError as exc:
                skipped_lines += 1
                error_window_start = max(exc.pos - 120, 0)
                error_window_end = min(exc.pos + 120, len(line))
                error_window = repr(line[error_window_start:error_window_end])[:200]
                warning_message = (
                    "VictoriaLogs query 返回非法 JSON 行，已跳过 | "
                    f"line_number={line_number} | "
                    f"line_length={len(line)} | "
                    f"error_position={exc.pos} | "
                    f"error={exc} | "
                    f"error_window_repr={error_window}"
                )
                logger.warning(
                    warning_message,
                    extra={
                        "line_number": line_number,
                        "error": str(exc),
                        "line_length": len(line),
                        "error_position": exc.pos,
                        "error_window_repr": error_window,
                    },
                )

        if skipped_lines:
            logger.warning(
                "VictoriaLogs query 解析存在非法行",
                extra={"skipped_lines": skipped_lines, "parsed_lines": len(result)},
            )

        return result

    def hits(self, query, start, end, field, fields_limit=5, step="5m"):
        fields_limit = VictoriaLogsConstants.normalize_hits_fields_limit(fields_limit, default=5, clamp=True)
        query = self._normalize_logsql_query(query)
        logger.info(
            "发送VictoriaLogs hits查询",
            extra={
                "query": query,
                "start": start,
                "end": end,
                "field": field,
                "fields_limit": fields_limit,
                "step": step,
            },
        )
        data = {
            "query": query,
            "start": start,
            "end": end,
            "field": field,
            "fields_limit": fields_limit,
            "step": step,
        }

        response = requests.post(
            self._build_url(self.host, "/select/logsql/hits"),
            params=data,
            auth=self.auth,
            verify=self.ssl_verify,
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def get_disk_usage(self):
        try:
            response = requests.get(
                self._build_url(self.host, "/metrics"),
                auth=self.auth,
                verify=self.ssl_verify,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            metrics_text = response.text
            storage_bytes = self._extract_metric_value(metrics_text, "vl_data_size_bytes", "storage")
            indexdb_bytes = self._extract_metric_value(metrics_text, "vl_data_size_bytes", "indexdb")
            used_bytes = storage_bytes + indexdb_bytes
            used_gb = round(used_bytes / (1024**3), 2)

            logger.info(
                "获取VictoriaLogs磁盘占用成功",
                extra={
                    "host": self.host,
                    "storage_bytes": storage_bytes,
                    "indexdb_bytes": indexdb_bytes,
                    "used_bytes": used_bytes,
                    "used_gb": used_gb,
                },
            )

            return {
                "used_gb": used_gb,
                "used_bytes": used_bytes,
                "storage_bytes": storage_bytes,
                "indexdb_bytes": indexdb_bytes,
                "unit": "GB",
            }
        except requests.RequestException as exc:
            logger.error(
                "获取VictoriaLogs磁盘占用失败",
                extra={"host": self.host, "error": str(exc), "error_type": type(exc).__name__},
            )
            raise
        except ValueError as exc:
            logger.error(
                "解析VictoriaLogs磁盘占用指标失败",
                extra={"host": self.host, "error": str(exc), "error_type": type(exc).__name__},
            )
            raise

    async def tail_async(self, query) -> AsyncIterator[str]:
        """异步版本的tail方法，ASGI兼容实现"""
        query = self._normalize_logsql_query(query)
        logger.info("发送VictoriaLogs tail查询", extra={"query": query})
        data = {"query": query}
        response = None

        try:
            logger.info(
                "开始异步VictoriaLogs tail请求",
                extra={
                    "host": self.host,
                    "query": query[:200] + "..." if len(query) > 200 else query,
                },
            )

            # 在线程池中执行同步请求，避免阻塞事件循环
            loop = asyncio.get_event_loop()

            def _make_request():
                response = requests.post(
                    self._build_url(self.host, "/select/logsql/tail"),
                    params=data,
                    auth=self.auth,
                    verify=self.ssl_verify,
                    stream=True,
                    timeout=(10, 120),  # 连接超时10秒，读取超时120秒
                    headers={
                        "Accept": "application/x-ndjson, text/plain",
                        "Connection": "keep-alive",
                        "Cache-Control": "no-cache",
                    },
                )
                response.raise_for_status()
                response.encoding = "utf-8"
                return response

            # 在执行器中运行同步请求
            response = await loop.run_in_executor(None, _make_request)

            logger.info(
                "异步VictoriaLogs tail响应成功",
                extra={"status_code": response.status_code},
            )

            # 异步生成器，逐行处理数据
            # 使用 asyncio.Queue 在线程与事件循环间传递数据：消费端可以
            # 真正挂起等待，生产端仍保留有界背压。
            _SENTINEL = object()
            line_queue: asyncio.Queue = asyncio.Queue(maxsize=256)
            stop_event = threading.Event()
            line_count = 0
            first_data_received = False
            start_time = time.time()

            def _put_unless_stopped(item) -> bool:
                """从生产线程向异步队列写入，并在消费端关闭时解除背压等待。"""
                if stop_event.is_set():
                    return False

                put_future = asyncio.run_coroutine_threadsafe(line_queue.put(item), loop)
                while True:
                    try:
                        put_future.result(timeout=0.1)
                        return True
                    except FutureTimeoutError:
                        if stop_event.is_set():
                            put_future.cancel()
                            return False

            def _iter_lines_in_thread():
                """在独立线程中消费流式响应，结果放入 Queue 供异步生成器读取。"""
                try:
                    for line in response.iter_lines(chunk_size=8192, decode_unicode=True):
                        if not _put_unless_stopped(line):
                            break
                except Exception as exc:
                    if not stop_event.is_set():
                        _put_unless_stopped(exc)
                finally:
                    if not stop_event.is_set():
                        _put_unless_stopped(_SENTINEL)

            try:
                # 流式读取使用独立 daemon 线程，避免异常上游长时间占用
                # ASGI 共享的默认 ThreadPoolExecutor。
                iter_thread = threading.Thread(
                    target=_iter_lines_in_thread,
                    name="victorialogs-tail-reader",
                    daemon=True,
                )
                iter_thread.start()

                while True:
                    item = await line_queue.get()

                    if item is _SENTINEL:
                        break
                    if isinstance(item, Exception):
                        raise item

                    line = item
                    if line:
                        line_count += 1

                        if not first_data_received:
                            elapsed = time.time() - start_time
                            logger.info(
                                "异步VictoriaLogs首个数据到达",
                                extra={"elapsed_time": elapsed},
                            )
                            first_data_received = True

                        try:
                            yield line.strip()

                            # 每1000行记录一次状态
                            if line_count % 1000 == 0:
                                logger.debug(
                                    "异步VictoriaLogs数据流状态",
                                    extra={
                                        "lines_received": line_count,
                                        "elapsed_time": time.time() - start_time,
                                    },
                                )

                        except Exception as line_error:
                            logger.warning(
                                "异步处理VictoriaLogs数据行失败",
                                extra={
                                    "error": str(line_error),
                                    "line_preview": line[:100] if line else "empty",
                                },
                            )
                            continue

            finally:
                stop_event.set()
                if response:
                    response.close()
                    logger.debug("VictoriaLogs响应连接已关闭")

                # 不在事件循环中阻塞 join；response.close() 会中断正在等待的
                # iter_lines，而满队列上的 put 最多 0.1 秒后观察到 stop_event。
                join_deadline = loop.time() + 1.0
                while iter_thread.is_alive() and loop.time() < join_deadline:
                    await asyncio.sleep(0.01)
                if iter_thread.is_alive():
                    logger.warning("VictoriaLogs tail 读取线程未在关闭期限内退出")

        except requests.exceptions.ConnectTimeout:
            logger.error("异步VictoriaLogs连接超时", extra={"host": self.host, "timeout": "10秒"})
            raise
        except requests.exceptions.ReadTimeout:
            logger.error(
                "异步VictoriaLogs读取超时",
                extra={"host": self.host, "timeout": "120秒"},
            )
            raise
        except Exception as e:
            logger.error(
                "异步VictoriaLogs tail错误",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise
        finally:
            # 双重保险：确保响应对象被关闭
            if response:
                try:
                    response.close()
                except:
                    pass  # 忽略关闭时的异常
