# -- coding: utf-8 --
# @File: query_vm.py
# @Time: 2025/11/12 11:27
# @Author: windyzhao
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


class Collection:
    def __init__(self):
        self.url = f"{VICTORIAMETRICS_HOST}/prometheus/api/v1/query"

    def query(
        self,
        sql,
        timeout=60,
        retries=DEFAULT_QUERY_RETRIES,
        retry_interval=DEFAULT_RETRY_INTERVAL,
        min_timestamp=None,
    ):
        """查询数据。

        默认查询最近 1 小时内的最新样本（``last_over_time(...[1h:])``）。
        传入 ``min_timestamp``（轮次 round_ts）时，窗口收紧为本轮起算的时长，
        并在客户端再过滤 ``value[0] >= min_timestamp``。
        """
        query_with_time = self._wrap_query(sql, min_timestamp=min_timestamp)
        params = {"query": query_with_time}
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
                    payload = resp.json()
                    return self._filter_by_min_timestamp(payload, min_timestamp)
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

    @staticmethod
    def _wrap_query(sql: str, min_timestamp=None) -> str:
        if min_timestamp is None:
            return f"last_over_time(({sql})[{DEFAULT_LOOKBACK}:])"
        try:
            round_ts = int(min_timestamp)
        except (TypeError, ValueError):
            return f"last_over_time(({sql})[{DEFAULT_LOOKBACK}:])"
        age = max(
            MIN_ROUND_LOOKBACK_SECONDS,
            int(time.time()) - round_ts + ROUND_LOOKBACK_BUFFER_SECONDS,
        )
        return f"last_over_time(({sql})[{age}s:])"

    @staticmethod
    def _filter_by_min_timestamp(payload, min_timestamp):
        if min_timestamp is None or not isinstance(payload, dict):
            return payload
        try:
            threshold = float(min_timestamp)
        except (TypeError, ValueError):
            return payload
        data = payload.get("data")
        if not isinstance(data, dict):
            return payload
        rows = data.get("result")
        if not isinstance(rows, list):
            return payload
        filtered = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if not isinstance(value, (list, tuple)) or not value:
                continue
            try:
                sample_ts = float(value[0])
            except (TypeError, ValueError):
                continue
            if sample_ts >= threshold:
                filtered.append(row)
        data = dict(data)
        data["result"] = filtered
        payload = dict(payload)
        payload["data"] = data
        return payload
