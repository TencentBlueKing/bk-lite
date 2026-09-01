# -*- coding: utf-8 -*-
"""FusionInsight 采集器：自包含 REST 实现（httpx，不依赖 SDK）。

移植自 old_plugins/.../resource_apis/cw_fusioninsight.py，保留其 HTTP/认证（login，
HTTP Basic）/handle_request/get_resource_uri/list_clusters/list_hosts 逻辑
（经过验证），仅去掉 old 框架依赖（cmp.cloud_apis.*、core.logger、
PrivateCloudManage、@register、双类 __getattr__ 分发、监控相关方法），并把原始字段
重命名为 CMDB 模型 attr 字段 + 关联用隐藏字段（cluster_id）。

设计要点：FusionInsight 平台对象无可采集业务字段（仅 inst_name/organization），故
本采集器不输出平台对象，只输出 cluster/host 两类（平台=采集任务自身实例，cluster
在 server 端 belong 到任务实例）。

输出结构：{"result": {"fusioninsight_cluster":[...], "fusioninsight_host":[...]},
"success": bool}
"""
import base64

import httpx
from sanic.log import logger


def get_resource_uri(op, basic_url, **kwargs):
    supported_ops = {
        "get_session": "{basic_url}/api/v2/session/status",
        "get_hosts": "{basic_url}/api/v2/hosts",
        "get_clusters": "{basic_url}/api/v2/clusters",
    }
    if op not in supported_ops:
        raise Exception(f"操作:{op}不存在,请检查supported_ops中是否包含该操作")
    return supported_ops[op].format(basic_url=basic_url, **kwargs)


def _str2base64(string):
    return base64.b64encode(string.encode("utf-8")).decode("utf-8")


async def handle_request(method, url, client: httpx.AsyncClient, **kwargs):
    try:
        resp = await client.request(method, url, **kwargs)
    except Exception:
        logger.exception("event=fusioninsight_http_failed url=%s method=%s", url, method)
        return {"result": False, "message": f"请求失败,url:{url},method:{method}", "data": {}}
    if resp.status_code > 300:
        logger.error(
            "event=fusioninsight_http_failed url=%s method=%s status_code=%s",
            url,
            method,
            resp.status_code,
        )
        return {
            "result": False,
            "message": f"请求错误,status_code:{resp.status_code},message:{resp.text}",
            "data": {},
        }
    logger.debug("event=fusioninsight_http_ok url=%s method=%s", url, method)
    return {"result": True, "data": resp.json() if resp.content else {}}


def _filter_obj_fields(obj, fields):
    return {field: obj[field] for field in fields if field in obj}


def _filter_obj_fields_by_list(objs, fields):
    return [_filter_obj_fields(obj, fields) for obj in objs]


def _safe_str(value):
    """None/空 → 空串；否则转字符串。避免 str(None)=='None' 脏数据。"""
    if value is None or value == "":
        return ""
    return str(value)


class FusionInsightManager:
    """FusionInsight 平台采集器。自包含 HTTP Basic 认证 + 资源拉取。"""

    def __init__(self, params: dict):
        self.params = params or {}
        self.account = self.params.get("username") or self.params.get("accessKey")
        self.password = self.params.get("password") or self.params.get("accessSecret")
        self.region = self.params.get("region", "") or ""
        self.host = self.params.get("host", "") or ""
        self.collection_task_id = self.params.get("collection_task_id")
        self.scheme = self.params.get("scheme", "https") or "https"
        self.port = int(self.params.get("port", 443))
        raw_verify_tls = self.params.get("verify_tls", True)
        self.verify_tls = (
            raw_verify_tls
            if isinstance(raw_verify_tls, bool)
            else str(raw_verify_tls).strip().lower() in {"1", "true", "yes", "on"}
        )
        port_suffix = "" if self.port == 443 else f":{self.port}"
        self.basic_url = f"{self.scheme}://{self.host}{port_suffix}/web"
        self.cw_headers = {"Content-Type": "application/json"}
        self._client: httpx.AsyncClient | None = None
        self._authed = False

    async def login(self):
        if self._client is None:
            self._client = httpx.AsyncClient(verify=self.verify_tls, timeout=60.0)
        new_string = _str2base64(f"{self.account}:{self.password}")
        headers = {"Authorization": f"Basic {new_string}"}
        url = get_resource_uri("get_session", self.basic_url)
        resp = await handle_request(
            "GET",
            url,
            client=self._client,
            headers=headers,
        )
        if not resp["result"]:
            raise Exception(resp["message"])
        return self._client

    async def _ensure_auth(self):
        if not self._authed:
            await self.login()
            self._authed = True
        return self._client

    async def list_clusters(self, **kwargs):
        await self._ensure_auth()
        url = get_resource_uri("get_clusters", self.basic_url)
        resp = await handle_request(
            "GET",
            url,
            client=self._client,
            headers=self.cw_headers,
        )
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        data = _filter_obj_fields_by_list(resp["data"], ["id", "name"])
        return {"result": True, "data": data}

    async def list_hosts(self, **kwargs):
        await self._ensure_auth()
        url = get_resource_uri("get_hosts", self.basic_url)
        params = {"no_page": True}
        resp = await handle_request(
            "GET",
            url,
            client=self._client,
            params=params,
            headers=self.cw_headers,
        )
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        hosts = resp["data"].get("hosts", []) if isinstance(resp["data"], dict) else []
        data = _filter_obj_fields_by_list(
            hosts,
            [
                "hostname", "ip", "cpuCores", "totalMemory", "totalHardDiskSpace",
                "runningStatus", "osType", "clusterName", "clusterId",
            ],
        )
        return {"result": True, "data": data}

    @staticmethod
    def _map_cluster(raw: dict) -> dict:
        return {
            "resource_name": raw.get("name", ""),
            "resource_id": _safe_str(raw.get("id")),
        }

    @staticmethod
    def _map_host(raw: dict) -> dict:
        return {
            "resource_name": raw.get("hostname", ""),
            "resource_id": raw.get("hostname", ""),
            "ip_addr": raw.get("ip", ""),
            "vcpus": _safe_str(raw.get("cpuCores")),
            "memory_mb": _safe_str(raw.get("totalMemory")),
            "storage_gb": _safe_str(raw.get("totalHardDiskSpace")),
            "status": raw.get("runningStatus", ""),
            "os_name": raw.get("osType", ""),
            "cluster_id": _safe_str(raw.get("clusterId")),
        }

    @staticmethod
    def _unwrap(resp):
        if not resp or not resp.get("result"):
            raise RuntimeError(resp.get("message") if isinstance(resp, dict) else "fusioninsight collect failed")
        return resp.get("data", []) or []

    async def get_clusters(self):
        return [self._map_cluster(raw) for raw in self._unwrap(await self.list_clusters())]

    async def get_hosts(self):
        return [self._map_host(raw) for raw in self._unwrap(await self.list_hosts())]

    async def exec_script(self):
        clusters = await self.get_clusters()
        hosts = await self.get_hosts()
        return {
            "fusioninsight_cluster": clusters,
            "fusioninsight_host": hosts,
        }

    async def list_all_resources(self):
        try:
            result = await self.exec_script()
            return {"result": result, "success": True}
        except Exception as err:  # noqa: BLE001
            logger.exception(
                "event=fusioninsight_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                self.host,
                self.collection_task_id,
                "list_all_resources",
                type(err).__name__,
            )
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
        finally:
            if self._client is not None:
                await self._client.aclose()
                self._client = None
                self._authed = False
