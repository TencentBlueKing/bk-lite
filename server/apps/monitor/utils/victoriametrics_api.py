import requests

from apps.core.logger import celery_logger as logger
from apps.monitor.constants.victoriametrics import VictoriaMetricsConstants


class VictoriaMetricsAPI:
    def __init__(self):
        self.host = VictoriaMetricsConstants.HOST
        self.username = VictoriaMetricsConstants.USER
        self.password = VictoriaMetricsConstants.PWD
        # 添加SSL验证配置，支持环境变量控制
        self.ssl_verify = VictoriaMetricsConstants.SSL_VERIFY
        self.timeout = VictoriaMetricsConstants.REQUEST_TIMEOUT

    def _do_get(self, api_path, params):
        try:
            response = requests.get(
                f"{self.host}{api_path}",
                params=params,
                auth=(self.username, self.password),
                verify=self.ssl_verify,  # 添加SSL验证配置
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            logger.error(
                "VictoriaMetrics request timed out",
                extra={
                    "host": self.host,
                    "api_path": api_path,
                    "timeout": self.timeout,
                },
                exc_info=True,
            )
            raise
        except requests.RequestException:
            logger.error(
                "VictoriaMetrics request failed",
                extra={
                    "host": self.host,
                    "api_path": api_path,
                },
                exc_info=True,
            )
            raise

    def query(self, query, step="5m", time=None):
        params = {"query": query}
        if step:
            params["step"] = step
        if time:
            params["time"] = time
        return self._do_get("/api/v1/query", params)

    def query_range(self, query, start, end, step="5m"):
        return self._do_get(
            "/api/v1/query_range",
            {"query": query, "start": start, "end": end, "step": step},
        )

    def labels(self, match=None):
        params = {}
        if match:
            params["match[]"] = match
        return self._do_get("/api/v1/labels", params)
