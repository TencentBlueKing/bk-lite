# -*- coding: utf-8 -*-
"""InfluxDB Information Collector（协议采集，兼容 1.x/2.x，优先 2.x）。

2.x：GET /health 取版本；GET /api/v2/config（operator token）取运行配置。
1.x：GET /ping 响应头取版本；配置类字段 API 不暴露，留空。
"""
import requests
from sanic.log import logger

try:  # 关闭自签证书告警
    requests.packages.urllib3.disable_warnings()
except Exception:  # noqa
    pass


class InfluxdbInfo:
    """采集 InfluxDB 实例配置信息。"""

    def __init__(self, kwargs):
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 8086))
        # 2.x 用 operator token；兼容传 password
        self.token = kwargs.get("token") or kwargs.get("password", "")
        self.ssl = str(kwargs.get("ssl", "")).lower() in ("1", "true", "yes")
        self.timeout = int(kwargs.get("timeout", 10))
        scheme = "https" if self.ssl else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}"

    def _get(self, path, headers=None):
        return requests.get(
            f"{self.base_url}{path}",
            headers=headers or {},
            timeout=self.timeout,
            verify=False,
        )

    def _collect_v2(self):
        """2.x：/health + /api/v2/config。"""
        model = {}
        try:
            hj = self._get("/health").json() or {}
            model["version"] = hj.get("version", "")
        except Exception:  # noqa
            model["version"] = ""

        headers = {"Authorization": f"Token {self.token}"} if self.token else {}
        resp = self._get("/api/v2/config", headers=headers)
        if resp.status_code == 200:
            body = resp.json() or {}
            cfg = body.get("config", body)
            model["data_dir"] = cfg.get("engine-path", "")
            model["wal_dir"] = cfg.get("wal-path", "") or cfg.get("engine-path", "")
            model["meta_dir"] = cfg.get("bolt-path", "")
            model["engine"] = cfg.get("storage-engine", "") or "tsm1"
            model["http_bind_address"] = cfg.get("http-bind-address", "")
            model["max_concurrent_queries"] = str(cfg.get("query-concurrency", ""))
        model["auth_enabled"] = "true"  # 2.x 强制开启认证
        return model

    def _collect_v1(self):
        """1.x：/ping 头取版本；路径类配置 API 不暴露，留空。"""
        model = {}
        try:
            resp = self._get("/ping")
            model["version"] = resp.headers.get("X-Influxdb-Version", "")
        except Exception:  # noqa
            model["version"] = ""
        return model

    def list_all_resources(self):
        """返回标准格式：{"result": {"influxdb": [model_data]}, "success": True}。"""
        try:
            try:
                health = self._get("/health")
                if health.status_code == 200 and "version" in (health.json() or {}):
                    model_data = self._collect_v2()
                else:
                    model_data = self._collect_v1()
            except Exception:  # noqa  health 不存在 → 走 1.x
                model_data = self._collect_v1()

            model_data["ip_addr"] = self.host
            model_data["port"] = self.port
            model_data["https_enabled"] = "true" if self.ssl else "false"
            inst_data = {"result": {"influxdb": [model_data]}, "success": True}
        except Exception as err:  # noqa
            import traceback
            logger.error(f"influxdb_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data
