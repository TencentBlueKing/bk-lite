# -- coding: utf-8 --
# @File: query_vm.py
# @Time: 2025/11/12 11:27
# @Author: windyzhao
import math
import time

import requests

from apps.cmdb.constants.constants import VICTORIAMETRICS_HOST
from apps.core.logger import cmdb_logger as logger

"""
VM查询的封装
"""

# 默认重试次数与退避基数；VictoriaMetrics 瞬时抖动（连接异常 / 5xx）时重试，
# 避免把一次瞬时故障放大成整轮采集失败。4xx 视为请求本身问题，不重试。
DEFAULT_QUERY_RETRIES = 3
DEFAULT_RETRY_INTERVAL = 1
DEFAULT_LOOKBACK = "1h"
# 轮次窗口相对 round_ts 的额外缓冲（秒），吸收时钟偏差与 flush 延迟。
ROUND_LOOKBACK_BUFFER_SECONDS = 120
MIN_ROUND_LOOKBACK_SECONDS = 60
RAW_TIMESTAMP_METRIC_NAME_LABEL = "__cmdb_metric_name__"


class Collection:
    def __init__(self):
        self.url = f"{VICTORIAMETRICS_HOST.rstrip('/')}/prometheus/api/v1/query"

    def query(
        self,
        sql,
        timeout=60,
        retries=DEFAULT_QUERY_RETRIES,
        retry_interval=DEFAULT_RETRY_INTERVAL,
        min_timestamp=None,
        max_timestamp=None,
        lookback_seconds=None,
        evaluation_time=None,
    ):
        """查询数据。

        默认查询最近 1 小时内的最新样本（``last_over_time(...[1h:])``）。
        传入 ``min_timestamp``（轮次开始时间）时，通过 ``tlast_over_time`` 取得
        原始样本时间，只返回完整轮次范围内的原指标值。``max_timestamp`` 未提供时
        以当前时间作为兼容上界。
        """
        if min_timestamp is not None:
            try:
                started_at = float(min_timestamp)
                completed_at = float(max_timestamp) if max_timestamp is not None else time.time()
            except (TypeError, ValueError):
                started_at = None
            if started_at is not None and completed_at >= started_at:
                return self._query_completed_round(
                    sql,
                    started_at=started_at,
                    completed_at=completed_at,
                    timeout=timeout,
                    retries=retries,
                    retry_interval=retry_interval,
                )

        query_with_time = self._wrap_latest_query(sql, lookback_seconds=lookback_seconds)
        return self._execute_query(
            query_with_time,
            timeout=timeout,
            retries=retries,
            retry_interval=retry_interval,
            evaluation_time=evaluation_time,
        )

    def _execute_query(
        self,
        query,
        *,
        timeout,
        retries,
        retry_interval,
        evaluation_time=None,
    ):
        params = {"query": query}
        if evaluation_time is not None:
            params["time"] = evaluation_time
        attempts = max(1, int(retries))
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                resp = requests.post(self.url, data=params, timeout=timeout)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("VM query connection error (attempt %d/%d): %s", attempt, attempts, exc)
            else:
                if resp.status_code == 200:
                    return resp.json()
                # 4xx 是请求本身的问题，重试无意义，立即抛出。
                if 400 <= resp.status_code < 500:
                    raise Exception(f"request error!{resp.text}")
                last_error = Exception(f"request error!{resp.text}")
                logger.warning(
                    "VM query server error (attempt %d/%d): status=%s",
                    attempt,
                    attempts,
                    resp.status_code,
                )

            if attempt < attempts:
                time.sleep(retry_interval * attempt)

        raise last_error if last_error is not None else Exception("VM query failed")

    def query_sample_timestamps(
        self,
        sql,
        *,
        lookback_seconds,
        evaluation_time=None,
        timeout=60,
        retries=DEFAULT_QUERY_RETRIES,
        retry_interval=DEFAULT_RETRY_INTERVAL,
    ):
        """查询每条序列最后一个原始样本时间，时间值位于结果 ``value[1]``。"""
        try:
            seconds = max(MIN_ROUND_LOOKBACK_SECONDS, int(lookback_seconds))
        except (TypeError, ValueError):
            seconds = MIN_ROUND_LOOKBACK_SECONDS
        payload = self._execute_query(
            (f'tlast_over_time((label_move(({sql}), "__name__", ' f'"{RAW_TIMESTAMP_METRIC_NAME_LABEL}"))[{seconds}s:])'),
            timeout=timeout,
            retries=retries,
            retry_interval=retry_interval,
            evaluation_time=evaluation_time,
        )
        rows = ((payload or {}).get("data") or {}).get("result") or []
        for row in rows:
            metric = row.get("metric") if isinstance(row, dict) else None
            if not isinstance(metric, dict):
                continue
            metric_name = metric.pop(RAW_TIMESTAMP_METRIC_NAME_LABEL, None)
            if metric_name not in (None, ""):
                metric["__name__"] = metric_name
        return payload

    @staticmethod
    def _wrap_latest_query(sql: str, *, lookback_seconds=None) -> str:
        if lookback_seconds is None:
            lookback = DEFAULT_LOOKBACK
        else:
            try:
                seconds = int(lookback_seconds)
            except (TypeError, ValueError):
                seconds = 0
            lookback = f"{seconds}s" if seconds > 0 else DEFAULT_LOOKBACK
        return f"last_over_time(({sql})[{lookback}:])"

    def _query_completed_round(
        self,
        sql,
        *,
        started_at,
        completed_at,
        timeout,
        retries,
        retry_interval,
    ):
        lookback = max(
            MIN_ROUND_LOOKBACK_SECONDS,
            math.ceil(completed_at - started_at + ROUND_LOOKBACK_BUFFER_SECONDS),
        )
        value_payload = self._execute_query(
            f"last_over_time(({sql})[{lookback}s:])",
            timeout=timeout,
            retries=retries,
            retry_interval=retry_interval,
            evaluation_time=completed_at,
        )
        timestamp_payload = self.query_sample_timestamps(
            sql,
            lookback_seconds=lookback,
            evaluation_time=completed_at,
            timeout=timeout,
            retries=retries,
            retry_interval=retry_interval,
        )
        return self._filter_by_raw_sample_time(
            value_payload,
            timestamp_payload,
            started_at=started_at,
            completed_at=completed_at,
        )

    @staticmethod
    def metric_key(row):
        metric = row.get("metric") if isinstance(row, dict) else None
        if not isinstance(metric, dict):
            return None
        return tuple(sorted((str(key), str(value)) for key, value in metric.items()))

    @classmethod
    def _filter_by_raw_sample_time(
        cls,
        value_payload,
        timestamp_payload,
        *,
        started_at,
        completed_at,
    ):
        if not isinstance(value_payload, dict):
            return value_payload
        timestamp_rows = ((timestamp_payload or {}).get("data") or {}).get("result") or []
        raw_timestamps = {}
        for row in timestamp_rows:
            key = cls.metric_key(row)
            value = row.get("value") if isinstance(row, dict) else None
            if key is None or not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            try:
                raw_timestamps[key] = float(value[1])
            except (TypeError, ValueError):
                continue

        data = value_payload.get("data")
        if not isinstance(data, dict):
            return value_payload
        rows = data.get("result")
        if not isinstance(rows, list):
            return value_payload
        filtered = []
        for row in rows:
            sample_ts = raw_timestamps.get(cls.metric_key(row))
            if sample_ts is not None and started_at <= sample_ts <= completed_at:
                filtered.append(row)
        data = dict(data)
        data["result"] = filtered
        payload = dict(value_payload)
        payload["data"] = data
        return payload

    @staticmethod
    def _wrap_query(sql: str, min_timestamp=None) -> str:
        """兼容旧测试/调用方；新轮次查询由 ``query`` 内部的双查询实现。"""
        if min_timestamp is None:
            return Collection._wrap_latest_query(sql)
        try:
            round_ts = int(min_timestamp)
        except (TypeError, ValueError):
            return f"last_over_time(({sql})[{DEFAULT_LOOKBACK}:])"
        age = max(
            MIN_ROUND_LOOKBACK_SECONDS,
            int(time.time()) - round_ts + ROUND_LOOKBACK_BUFFER_SECONDS,
        )
        return f"last_over_time(({sql})[{age}s:])"
