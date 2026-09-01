# -*- coding: utf-8 -*-
"""InfluxDB Information Collector（协议采集，兼容 1.x/2.x，优先 2.x）。

2.x：GET /health 取版本；GET /api/v2/config（operator token）取运行配置。
1.x：GET /ping 响应头取版本；配置类字段 API 不暴露，留空。
"""
import httpx
from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from sanic.log import logger


class InfluxdbInfo:
    """采集 InfluxDB 实例配置信息。"""

    def __init__(self, kwargs):
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 8086))
        # 2.x 用 operator token；兼容传 password
        self.token = kwargs.get("token") or kwargs.get("password", "")
        self.ssl = str(kwargs.get("ssl", "")).lower() in ("1", "true", "yes")
        self.verify_tls = self._as_bool(kwargs.get("verify_tls"), default=True)
        self.timeout = 10  # 请求超时硬编码；表单 timeout 由框架作单对象预算
        scheme = "https" if self.ssl else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}"
        self.collection_task_id = kwargs.get("collection_task_id")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            verify=self.verify_tls,
        )

    async def _get(self, client: httpx.AsyncClient, path, headers=None):
        return await client.get(
            f"{self.base_url}{path}",
            headers=headers or {},
        )

    async def probe(self) -> AccessProbeResult:
        try:
            async with self._client() as client:
                response = await self._get(client, "/health")
                body = response.json() if response.content else {}
                if response.status_code == 200 and body.get("version"):
                    version = str(body["version"])
                else:
                    response = await self._get(client, "/ping")
                    version = str(response.headers.get("X-Influxdb-Version") or "")
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
                config = await self._get(
                    client,
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
        except httpx.TimeoutException:
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_probe_no_response",
            )
        except httpx.HTTPError as err:
            message = str(err).lower()
            if "certificate" in message or "ssl" in message or "tls" in message:
                return AccessProbeResult(
                    status=AccessProbeStatus.TLS_VALIDATION_FAILED,
                    error_code="tls_validation_failed",
                )
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

    async def _collect_v2(self, client: httpx.AsyncClient, health):
        """2.x：健康信息始终可采；仅在用户提供 Token 后读取运行配置。"""
        model = {"version": (health or {}).get("version", "")}
        model["auth_enabled"] = "true"  # 2.x 强制开启认证
        warning = ""
        if not self.token:
            return model, warning

        try:
            resp = await self._get(
                client,
                "/api/v2/config",
                headers={"Authorization": f"Token {self.token}"},
            )
            if resp.status_code != 200:
                warning = (
                    "Operator Token 无效或权限不足，无法读取 InfluxDB 运行配置" if resp.status_code in (401, 403) else f"InfluxDB 运行配置接口返回 HTTP {resp.status_code}"
                )
                return model, warning

            body = resp.json() if resp.content else {}
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

    async def _collect_v1(self, client: httpx.AsyncClient):
        """1.x：/ping 头取版本；路径类配置 API 不暴露，留空。"""
        resp = await self._get(client, "/ping")
        return {"version": resp.headers.get("X-Influxdb-Version", "")}

    async def list_all_resources(self):
        """返回标准格式：{"result": {"influxdb": [model_data]}, "success": True}。"""
        try:
            async with self._client() as client:
                try:
                    health_response = await self._get(client, "/health")
                    health = health_response.json() if health_response.content else {}
                    if health_response.status_code == 200 and "version" in health:
                        model_data, warning = await self._collect_v2(client, health)
                    else:
                        model_data = await self._collect_v1(client)
                        warning = ""
                except Exception:  # noqa  health 不存在 → 走 1.x
                    model_data = await self._collect_v1(client)
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
                return {"result": {"influxdb": rows}, "success": True}
        except Exception as err:  # noqa
            logger.exception(
                "event=influxdb_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                self.host,
                self.collection_task_id,
                "list_all_resources",
                type(err).__name__,
            )
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
