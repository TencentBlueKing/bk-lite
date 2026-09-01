import requests
from requests.adapters import HTTPAdapter

from apps.core.logger import celery_logger as logger
from apps.monitor.constants.victoriametrics import VictoriaMetricsConstants

# 模块级 Session，复用 TCP/TLS 连接，避免详情页 N 次指标卡各自新建连接。
_SESSION = requests.Session()
_ADAPTER = HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0)
_SESSION.mount("http://", _ADAPTER)
_SESSION.mount("https://", _ADAPTER)


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
            response = _SESSION.get(
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

    def _do_get_allow_error(self, api_path, params):
        """GET that returns (payload, http_error) for PromQL/HTTP failures.

        Network/timeouts still raise so callers can classify infra errors.
        HTTP 4xx/5xx with a JSON body return that body plus the HTTPError.
        """
        try:
            response = _SESSION.get(
                f"{self.host}{api_path}",
                params=params,
                auth=(self.username, self.password),
                verify=self.ssl_verify,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json(), None
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
        except requests.HTTPError as exc:
            payload = None
            resp = getattr(exc, "response", None)
            if resp is not None:
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {"error": (resp.text or "")[:200]}
            return payload, exc
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

    def query(self, query, step="5m", time=None, lookback_delta=None):
        params = {"query": query}
        if step:
            params["step"] = step
        if time:
            params["time"] = time
        if lookback_delta:
            params["lookback_delta"] = lookback_delta
        return self._do_get("/api/v1/query", params)

    def query_allow_error(self, query, step="5m", time=None, lookback_delta=None):
        """Instant query that surfaces PromQL/HTTP errors without raising."""
        params = {"query": query}
        if step:
            params["step"] = step
        if time:
            params["time"] = time
        if lookback_delta:
            params["lookback_delta"] = lookback_delta
        return self._do_get_allow_error("/api/v1/query", params)

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

    def label_values(self, label, match=None):
        """Return values for a label name, optionally scoped by match[]."""
        params = {}
        if match:
            params["match[]"] = match
        return self._do_get(f"/api/v1/label/{label}/values", params)
