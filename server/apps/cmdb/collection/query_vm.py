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


class Collection:
    def __init__(self):
        self.url = f"{VICTORIAMETRICS_HOST}/prometheus/api/v1/query"

    def query(self, sql, timeout=60, retries=DEFAULT_QUERY_RETRIES, retry_interval=DEFAULT_RETRY_INTERVAL):
        """查询数据 - 查询最近1小时内的最新数据。

        对连接类异常与 5xx 做有限次退避重试；4xx 直接失败（重试无意义）。
        """
        query_with_time = f"last_over_time({sql}[1h])"
        params = {"query": query_with_time}
        attempts = max(1, int(retries))
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                resp = requests.post(self.url, data=params, timeout=timeout)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "VM query connection error (attempt %d/%d): %s", attempt, attempts, exc
                )
            else:
                if resp.status_code == 200:
                    return resp.json()
                # 4xx 是请求本身的问题，重试无意义，立即抛出。
                if 400 <= resp.status_code < 500:
                    raise Exception(f"request error!{resp.text}")
                last_error = Exception(f"request error!{resp.text}")
                logger.warning(
                    "VM query server error (attempt %d/%d): status=%s",
                    attempt, attempts, resp.status_code,
                )

            if attempt < attempts:
                time.sleep(retry_interval * attempt)

        raise last_error if last_error is not None else Exception("VM query failed")
