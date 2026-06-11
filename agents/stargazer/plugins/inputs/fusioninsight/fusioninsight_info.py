# -*- coding: utf-8 -*-
"""FusionInsight 采集器：自包含 REST 实现（requests，不依赖 SDK）。

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
import traceback

from sanic.log import logger

# `requests` 仅在真正发起 HTTP 时才需要；延迟导入，保证模块（含纯函数与字段重命名）
# 在未安装 requests 的精简环境下也可导入与单测。
try:  # pragma: no cover - 取决于运行环境是否装了 requests
    import requests
except ImportError:  # pragma: no cover
    requests = None


# fusioninsight api 接口枚举（路径与 old get_resource_uri 完全一致）
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


def handle_request(method, url, session=None, **kwargs):
    if requests is None:
        raise RuntimeError(
            "FusionInsight 采集需要 requests 库，但当前运行环境未安装 requests，请在 stargazer 运行环境安装后重试"
        )
    _requests = session or requests
    try:
        resp = _requests.request(method, url, **kwargs)
    except Exception:
        logger.exception(f"fusioninsight 请求失败,url:{url},method:{method}")
        return {"result": False, "message": f"请求失败,url:{url},method:{method}", "data": {}}
    if resp.status_code > 300:
        logger.error(
            f"fusioninsight 请求失败,url:{url},method:{method},"
            f"status_code:{resp.status_code},message:{resp.content.decode('utf-8')}"
        )
        return {
            "result": False,
            "message": f"请求错误,status_code:{resp.status_code},message:{resp.content.decode('utf-8')}",
            "data": {},
        }
    logger.info(f"fusioninsight 请求成功,url:{url},method:{method}")
    return {"result": True, "data": resp.json()}


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
        self.scheme = self.params.get("scheme", "https") or "https"
        self.basic_url = f"{self.scheme}://{self.host}/web"
        self.cw_headers = {"Content-Type": "application/json"}
        self._handle_request = handle_request
        self._session = None
        self._authed = False

    # ----------------------------------------------------------------------
    # 认证（移植 old login，HTTP Basic + session 复用，逻辑保持不变）
    # ----------------------------------------------------------------------
    def login(self):
        if requests is None:
            raise RuntimeError(
                "FusionInsight 采集需要 requests 库，但当前运行环境未安装 requests，请在 stargazer 运行环境安装后重试"
            )
        self._session = requests.Session()
        new_string = _str2base64(f"{self.account}:{self.password}")
        headers = {"Authorization": f"Basic {new_string}"}
        url = get_resource_uri("get_session", self.basic_url)
        resp = self._handle_request("GET", url, session=self._session, headers=headers, verify=False)
        if not resp["result"]:
            raise Exception(resp["message"])
        return self._session

    def _ensure_auth(self):
        if not self._authed:
            self.login()
            self._authed = True
        return self._session

    # ----------------------------------------------------------------------
    # list_*（移植 old，返回原始资源字段过滤结果）
    # ----------------------------------------------------------------------
    def list_clusters(self, **kwargs):
        self._ensure_auth()
        url = get_resource_uri("get_clusters", self.basic_url)
        resp = self._handle_request("GET", url, session=self._session, headers=self.cw_headers, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        data = _filter_obj_fields_by_list(resp["data"], ["id", "name"])
        return {"result": True, "data": data}

    def list_hosts(self, **kwargs):
        self._ensure_auth()
        url = get_resource_uri("get_hosts", self.basic_url)
        params = {"no_page": True}
        resp = self._handle_request(
            "GET", url, session=self._session, params=params, headers=self.cw_headers, verify=False
        )
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        # old 行为：主机列表在 resp["data"]["hosts"]
        hosts = resp["data"].get("hosts", []) if isinstance(resp["data"], dict) else []
        data = _filter_obj_fields_by_list(
            hosts,
            [
                "hostname", "ip", "cpuCores", "totalMemory", "totalHardDiskSpace",
                "runningStatus", "osType", "clusterName", "clusterId",
            ],
        )
        return {"result": True, "data": data}

    # ----------------------------------------------------------------------
    # 字段重命名纯函数（原始字段 → 模型 attr 字段 + 隐藏关联字段）
    # ----------------------------------------------------------------------
    @staticmethod
    def _map_cluster(raw: dict) -> dict:
        return {
            "resource_name": raw.get("name", ""),
            # format/collect.py 口径：resource_id = str(id)，即使是数字也转 str
            "resource_id": _safe_str(raw.get("id")),
        }

    @staticmethod
    def _map_host(raw: dict) -> dict:
        # 注意：totalMemory / totalHardDiskSpace 的单位（MB? GB?）由 FusionInsight API
        # 决定，old collect.py 直传未做单位换算，此处沿用原始值（仅 _safe_str 防 None）。
        # 需真机核对其单位是否符合模型 memory_mb / storage_gb 语义，必要时再加换算。
        return {
            "resource_name": raw.get("hostname", ""),
            "resource_id": raw.get("hostname", ""),
            "ip_addr": raw.get("ip", ""),
            "vcpus": _safe_str(raw.get("cpuCores")),
            "memory_mb": _safe_str(raw.get("totalMemory")),
            "storage_gb": _safe_str(raw.get("totalHardDiskSpace")),
            "status": raw.get("runningStatus", ""),
            "os_name": raw.get("osType", ""),
            # 隐藏关联字段：host belong cluster。host belong 的集群 resource_id 是
            # str(cluster id)，故 cluster_id 与 cluster.resource_id 同为 str。
            "cluster_id": _safe_str(raw.get("clusterId")),
        }

    # ----------------------------------------------------------------------
    # get_*：拉原始列表 + 重命名（不实现 get_platform）
    # ----------------------------------------------------------------------
    @staticmethod
    def _unwrap(resp):
        if not resp or not resp.get("result"):
            raise RuntimeError(resp.get("message") if isinstance(resp, dict) else "fusioninsight collect failed")
        return resp.get("data", []) or []

    def get_clusters(self):
        return [self._map_cluster(raw) for raw in self._unwrap(self.list_clusters())]

    def get_hosts(self):
        return [self._map_host(raw) for raw in self._unwrap(self.list_hosts())]

    def exec_script(self):
        clusters = self.get_clusters()
        hosts = self.get_hosts()
        return {
            "fusioninsight_cluster": clusters,
            "fusioninsight_host": hosts,
        }

    def list_all_resources(self):
        try:
            result = self.exec_script()
            return {"result": result, "success": True}
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.__class__.__name__} error! {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
