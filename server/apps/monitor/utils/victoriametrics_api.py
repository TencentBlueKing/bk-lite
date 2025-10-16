import requests

from apps.log.constants import VICTORIALOGS_SSL_VERIFY
from apps.monitor.constants import VICTORIAMETRICS_HOST, VICTORIAMETRICS_USER, VICTORIAMETRICS_PWD


class VictoriaMetricsAPI:
    def __init__(self):
        self.host = VICTORIAMETRICS_HOST
        self.username = VICTORIAMETRICS_USER
        self.password = VICTORIAMETRICS_PWD
        # 添加SSL验证配置，支持环境变量控制
        self.ssl_verify = VICTORIALOGS_SSL_VERIFY

    def query(self, query, step="5m", time=None):
        params = {"query": query}
        if step:
            params["step"] = step
        if time:
            params["time"] = time
        response = requests.get(
            f"{self.host}/api/v1/query",
            params=params,
            auth=(self.username, self.password),
            verify=self.ssl_verify,  # 添加SSL验证配置
        )
        response.raise_for_status()
        return response.json()

    def query_range(self, query, start, end, step="5m"):
        response = requests.get(
            f"{self.host}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
            auth=(self.username, self.password),
            verify=self.ssl_verify,  # 添加SSL验证配置
        )
        response.raise_for_status()
        return response.json()
