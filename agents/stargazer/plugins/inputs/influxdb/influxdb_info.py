# -*- coding: utf-8 -*-
"""InfluxDB Information Collector（协议采集，兼容 1.x/2.x，优先 2.x）。

2.x：GET /health 取版本；GET /api/v2/config（operator token）取运行配置。
1.x：GET /ping 响应头取版本；配置类字段 API 不暴露，留空。
"""
import asyncio
import requests
from sanic.log import logger

from core.collection.contracts import (
    AccessProbeResult,
    AccessProbeStatus,
)

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
        self.verify_tls = self._as_bool(kwargs.get("verify_tls"), default=True)
        self.timeout = int(kwargs.get("timeout", 10))
        scheme = "https" if self.ssl else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}"

    def _get(self, path, headers=None):
        return requests.get(
            f"{self.base_url}{path}",
            headers=headers or {},
            timeout=self.timeout,
            verify=self.verify_tls,
        )

    async def probe(self) -> AccessProbeResult:
        return await asyncio.to_thread(self._probe_sync)

    def _probe_sync(self) -> AccessProbeResult:
        try:
            response = self._get("/health")
            body = response.json() or {}
            if response.status_code == 200 and body.get("version"):
                version = str(body["version"])
            else:
                response = self._get("/ping")
                version = str(
                    response.headers.get("X-Influxdb-Version") or ""
                )
                if response.status_code not in {200, 204} or not version:
                    return AccessProbeResult(
                        status=AccessProbeStatus.PROTOCOL_MISMATCH,
                        error_code="influxdb_protocol_mismatch",
                    )
            if not self.token:
                return AccessProbeResult(
                    status=AccessProbeStatus.READY,
                    evidence={"server_version": version},
                )
            config = self._get(
                "/api/v2/config",
                headers={"Authorization": f"Token {self.token}"},
            )
            if config.status_code == 401:
                return AccessProbeResult(
                    status=AccessProbeStatus.AUTH_FAILED,
                    error_code="authentication_failed",
                )
            if config.status_code == 403:
                return AccessProbeResult(
                    status=AccessProbeStatus.CAPABILITY_DENIED,
                    error_code="capability_denied",
                )
            if config.status_code == 429:
                return AccessProbeResult(
                    status=AccessProbeStatus.RATE_LIMITED,
                    error_code="rate_limited",
                )
            if config.status_code >= 500:
                return AccessProbeResult(
                    status=AccessProbeStatus.SERVICE_UNAVAILABLE,
                    error_code="service_unavailable",
                )
            if config.status_code != 200:
                return AccessProbeResult(
                    status=AccessProbeStatus.PROTOCOL_MISMATCH,
                    error_code="influxdb_protocol_mismatch",
                )
            return AccessProbeResult(
                status=AccessProbeStatus.READY,
                evidence={"server_version": version},
            )
        except requests.exceptions.SSLError:
            return AccessProbeResult(
                status=AccessProbeStatus.TLS_VALIDATION_FAILED,
                error_code="tls_validation_failed",
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_probe_no_response",
            )

    @staticmethod
    def _as_bool(value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _collect_v2(self, health):
        """2.x：健康信息始终可采；仅在用户提供 Token 后读取运行配置。"""
        model = {"version": (health or {}).get("version", "")}
        model["auth_enabled"] = "true"  # 2.x 强制开启认证
        warning = ""
        if not self.token:
            return model, warning

        try:
            resp = self._get(
                "/api/v2/config",
                headers={"Authorization": f"Token {self.token}"},
            )
            if resp.status_code != 200:
                warning = (
                    "Operator Token 无效或权限不足，无法读取 InfluxDB 运行配置"
                    if resp.status_code in (401, 403)
                    else f"InfluxDB 运行配置接口返回 HTTP {resp.status_code}"
                )
                return model, warning

            body = resp.json() or {}
            cfg = body.get("config", body)
            model.update(
                data_dir=cfg.get("engine-path", ""),
                wal_dir=cfg.get("wal-path", "") or cfg.get("engine-path", ""),
                meta_dir=cfg.get("bolt-path", ""),
                engine=cfg.get("storage-engine", "") or "tsm1",
                http_bind_address=cfg.get("http-bind-address", ""),
                max_concurrent_queries=str(cfg.get("query-concurrency", "")),
            )
        except Exception:  # noqa
            warning = "无法读取 InfluxDB 运行配置，请检查 Operator Token 与网络连接"
        return model, warning

    def _collect_v1(self):
        """1.x：/ping 头取版本；路径类配置 API 不暴露，留空。"""
        resp = self._get("/ping")
        return {"version": resp.headers.get("X-Influxdb-Version", "")}

    async def list_all_resources(self):
        return await asyncio.to_thread(self._list_all_resources_sync)

    def _list_all_resources_sync(self):
        """返回标准格式：{"result": {"influxdb": [model_data]}, "success": True}。"""
        try:
            try:
                health_response = self._get("/health")
                health = health_response.json() or {}
                if health_response.status_code == 200 and "version" in health:
                    model_data, warning = self._collect_v2(health)
                else:
                    model_data = self._collect_v1()
                    warning = ""
            except Exception:  # noqa  health 不存在 → 走 1.x
                model_data = self._collect_v1()
                warning = ""

            model_data["ip_addr"] = self.host
            model_data["port"] = self.port
            model_data["https_enabled"] = "true" if self.ssl else "false"
            rows = [model_data]
            if warning:
                rows.append(
                    {
                        "ip_addr": self.host,
                        "port": self.port,
                        "collect_status": "failed",
                        "collect_error": warning,
                    }
                )
            inst_data = {"result": {"influxdb": rows}, "success": True}
        except Exception as err:  # noqa
            import traceback
            logger.error(f"influxdb_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data
