# -*- coding: utf-8 -*-
"""SmartX 采集器：自包含 REST 实现（requests，不依赖 SDK）。

移植自 old_plugins/.../resource_apis/cw_smartx.py，保留其 HTTP/认证（login）/
handle_request/get_resource_uri/list_clusters/list_hosts/list_vms/list_vm_volumes
逻辑（经过验证），仅去掉 old 框架依赖（cmp.cloud_apis.*、core.logger、
PrivateCloudManage、@register、双类 __getattr__ 分发），并把原始字段重命名为
CMDB 模型 attr 字段 + 关联用隐藏字段（cluster_id）。

输出结构：{"result": {"smartx":[...], "smartx_cluster":[...], "smartx_host":[...],
"smartx_vm":[...], "smartx_vmvolume":[...]}, "success": bool}
"""
import traceback

from sanic.log import logger

# `requests` 仅在真正发起 HTTP 时才需要；延迟导入，保证模块（含纯函数与字段重命名）
# 在未安装 requests 的精简环境下也可导入与单测。
try:  # pragma: no cover - 取决于运行环境是否装了 requests
    import requests
except ImportError:  # pragma: no cover
    requests = None


# smartx api 接口枚举（路径与 old get_resource_uri 完全一致）
def get_resource_uri(op, basic_url, **kwargs):
    supported_ops = [
        "login",
        "get-clusters",
        "get-hosts",
        "get-vms",
        "get-vm-volumes",
    ]
    if op not in supported_ops:
        raise Exception(f"操作:{op}不存在,请检查supported_ops中是否包含该操作")
    return f"{basic_url}/v2/api/{op}"


def handle_request(method, url, **kwargs):
    if requests is None:
        raise RuntimeError(
            "SmartX 采集需要 requests 库，但当前运行环境未安装 requests，请在 stargazer 运行环境安装后重试"
        )
    try:
        resp = requests.request(method, url, **kwargs)
    except Exception:
        logger.exception(f"smartx 请求失败,url:{url},method:{method}")
        return {"result": False, "message": f"请求失败,url:{url},method:{method}", "data": {}}
    if resp.status_code > 300:
        logger.error(
            f"smartx 请求失败,url:{url},method:{method},"
            f"status_code:{resp.status_code},message:{resp.content.decode('utf-8')}"
        )
        return {
            "result": False,
            "message": f"请求错误,status_code:{resp.status_code},message:{resp.content.decode('utf-8')}",
            "data": {},
        }
    logger.info(f"smartx 请求成功,url:{url},method:{method}")
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


def _round_div(value, divisor):
    """换算并保留 3 位小数；缺失/异常时返回 ""。"""
    try:
        if value is None:
            return ""
        return str(round(float(value) / divisor, 3))
    except (TypeError, ValueError):
        return ""


class SmartXManager:
    """SmartX 私有云采集器。自包含登录认证 + 资源拉取。"""

    def __init__(self, params: dict):
        self.params = params or {}
        self.account = self.params.get("username") or self.params.get("accessKey")
        self.password = self.params.get("password") or self.params.get("accessSecret")
        self.region = self.params.get("region", "") or ""
        self.host = self.params.get("host", "") or ""
        self.scheme = self.params.get("scheme", "https") or "https"
        self.source = self.params.get("source", "LOCAL") or "LOCAL"
        self.basic_url = f"{self.scheme}://{self.host}"
        self.cw_headers = {"Content-Type": "application/json"}
        self._handle_request = handle_request
        self._token = None
        # host_id -> cluster_id 映射（get_hosts 时建立，供 get_vms 填隐藏字段）
        self._host_cluster_map = {}

    # ----------------------------------------------------------------------
    # 认证（移植 old login，逻辑保持不变）
    # ----------------------------------------------------------------------
    def login(self):
        if requests is None:
            raise RuntimeError(
                "SmartX 采集需要 requests 库，但当前运行环境未安装 requests，请在 stargazer 运行环境安装后重试"
            )
        data = {"username": self.account, "password": self.password, "source": self.source}
        url = get_resource_uri("login", self.basic_url)
        resp = self._handle_request("POST", url, json=data, headers=self.cw_headers, verify=False)
        if not resp["result"]:
            raise Exception(resp["message"])
        return resp["data"].get("data", {}).get("token", "")

    def _ensure_auth(self):
        if not self._token:
            self._token = self.login()
            self.cw_headers.update({"Authorization": self._token})
        return self._token

    # ----------------------------------------------------------------------
    # list_*（移植 old，返回原始资源字段过滤结果）
    # ----------------------------------------------------------------------
    def list_clusters(self, **kwargs):
        self._ensure_auth()
        url = get_resource_uri("get-clusters", self.basic_url)
        resp = self._handle_request("POST", url, headers=self.cw_headers, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        data = _filter_obj_fields_by_list(
            resp["data"],
            [
                "id", "name", "type", "architecture", "hypervisor", "version",
                "total_data_capacity", "total_cache_capacity", "total_cpu_cores",
                "total_memory_bytes", "datacenters",
            ],
        )
        return {"result": True, "data": data}

    def list_hosts(self, **kwargs):
        self._ensure_auth()
        url = get_resource_uri("get-hosts", self.basic_url)
        resp = self._handle_request("POST", url, headers=self.cw_headers, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        clusters_rsp = self.list_clusters()
        if not clusters_rsp["result"]:
            return {"result": False, "message": clusters_rsp["message"]}
        cluster_map = {cluster["id"]: cluster for cluster in clusters_rsp["data"]}
        data = _filter_obj_fields_by_list(
            resp["data"],
            [
                "id", "name", "cluster", "management_ip", "data_ip", "cpu_brand",
                "total_cpu_sockets", "total_data_capacity", "total_cache_capacity",
                "total_cpu_cores", "total_memory_bytes",
            ],
        )
        # old 行为：把每个 host 的 cluster 替换为完整 cluster 对象（含 architecture、id）
        for item in data:
            item["cluster"] = cluster_map.get(item.get("cluster", {}).get("id"), {})
        return {"result": True, "data": data}

    def list_vms(self, **kwargs):
        self._ensure_auth()
        url = get_resource_uri("get-vms", self.basic_url)
        resp = self._handle_request("POST", url, headers=self.cw_headers, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        data = _filter_obj_fields_by_list(
            resp["data"],
            ["id", "name", "host", "cluster", "status", "vcpu", "memory", "ips", "os"],
        )
        return {"result": True, "data": data}

    def list_vm_volumes(self, **kwargs):
        self._ensure_auth()
        url = get_resource_uri("get-vm-volumes", self.basic_url)
        resp = self._handle_request("POST", url, headers=self.cw_headers, verify=False)
        if not resp["result"]:
            return {"result": False, "message": resp["message"]}
        data = _filter_obj_fields_by_list(
            resp["data"],
            ["id", "name", "cluster", "size"],
        )
        return {"result": True, "data": data}

    # ----------------------------------------------------------------------
    # 字段重命名纯函数（原始字段 → 模型 attr 字段 + 隐藏关联字段）
    # ----------------------------------------------------------------------
    @staticmethod
    def _map_cluster(raw: dict) -> dict:
        datacenters = raw.get("datacenters", []) or []
        return {
            "resource_name": raw.get("name", ""),
            "resource_id": raw.get("id", ""),
            "cluster_type": raw.get("type", ""),
            "cpu_vendor": raw.get("architecture", ""),
            "hypervisor": raw.get("hypervisor", ""),
            "version": raw.get("version", ""),
            "datacenter": ",".join(i.get("name", "") for i in datacenters),
            "storage_gb": _round_div(raw.get("total_data_capacity", 0), 1024 * 1024 * 1024),
            "cache_gb": _round_div(raw.get("total_cache_capacity", 0), 1024 * 1024 * 1024),
            "vcpus": _safe_str(raw.get("total_cpu_cores")),
            "memory_mb": _round_div(raw.get("total_memory_bytes", 0), 1024 * 1024),
        }

    @staticmethod
    def _map_host(raw: dict) -> dict:
        cluster = raw.get("cluster", {}) or {}
        return {
            "resource_name": raw.get("name", ""),
            "resource_id": raw.get("id", ""),
            "ip_addr": raw.get("management_ip", ""),
            "data_ip": raw.get("data_ip", ""),
            "cpu_brand": raw.get("cpu_brand", ""),
            "cpu_arch": cluster.get("architecture", ""),
            "cpu_sockets": _safe_str(raw.get("total_cpu_sockets")),
            "storage_gb": _round_div(raw.get("total_data_capacity", 0), 1024 * 1024 * 1024),
            "cache_gb": _round_div(raw.get("total_cache_capacity", 0), 1024 * 1024 * 1024),
            "vcpus": _safe_str(raw.get("total_cpu_cores")),
            "memory_mb": _round_div(raw.get("total_memory_bytes", 0), 1024 * 1024),
        }

    @staticmethod
    def _map_vm(raw: dict, cluster_id: str = "") -> dict:
        ips = raw.get("ips", "")
        ip_addr = ",".join(ips) if isinstance(ips, list) else (ips or "")
        return {
            "resource_name": raw.get("name", ""),
            "resource_id": raw.get("id", ""),
            "status": raw.get("status", ""),
            "vcpus": _safe_str(raw.get("vcpu")),
            "memory_mb": _round_div(raw.get("memory", 0), 1024 * 1024),
            "ip_addr": ip_addr,
            "os": raw.get("os") or "",
            # 隐藏关联字段：建 vm→cluster 关联
            "cluster_id": cluster_id or "",
        }

    @staticmethod
    def _map_volume(raw: dict) -> dict:
        cluster = raw.get("cluster", {}) or {}
        return {
            "resource_name": raw.get("name", ""),
            "resource_id": raw.get("id", ""),
            "storage_gb": _round_div(raw.get("size", 0), 1024 * 1024 * 1024),
            # 隐藏关联字段：vmvolume 直接有 cluster.id
            "cluster_id": cluster.get("id", ""),
        }

    # ----------------------------------------------------------------------
    # get_*：拉原始列表 + 重命名
    # ----------------------------------------------------------------------
    @staticmethod
    def _unwrap(resp):
        if not resp or not resp.get("result"):
            raise RuntimeError(resp.get("message") if isinstance(resp, dict) else "smartx collect failed")
        return resp.get("data", []) or []

    def get_platform(self):
        """平台对象（smartx）：字段对齐 attr-smartx（global_domain_name）。"""
        return [{"global_domain_name": self.host}]

    def get_clusters(self):
        return [self._map_cluster(raw) for raw in self._unwrap(self.list_clusters())]

    def get_hosts(self):
        hosts = self._unwrap(self.list_hosts())
        # 顺便缓存 host_id -> cluster_id 映射，供 get_vms 填 vm 的隐藏 cluster_id
        for raw in hosts:
            cluster = raw.get("cluster", {}) or {}
            self._host_cluster_map[raw.get("id")] = cluster.get("id", "")
        return [self._map_host(raw) for raw in hosts]

    def get_vms(self):
        vms = []
        for raw in self._unwrap(self.list_vms()):
            host = raw.get("host", {}) or {}
            cluster_id = self._host_cluster_map.get(host.get("id"), "")
            vms.append(self._map_vm(raw, cluster_id=cluster_id))
        return vms

    def get_volumes(self):
        return [self._map_volume(raw) for raw in self._unwrap(self.list_vm_volumes())]

    def exec_script(self):
        clusters = self.get_clusters()
        hosts = self.get_hosts()  # 先建 host_id->cluster_id 映射
        vms = self.get_vms()      # 再据映射填 vm 的隐藏 cluster_id
        volumes = self.get_volumes()
        return {
            "smartx": self.get_platform(),
            "smartx_cluster": clusters,
            "smartx_host": hosts,
            "smartx_vm": vms,
            "smartx_vmvolume": volumes,
        }

    def list_all_resources(self):
        try:
            result = self.exec_script()
            return {"result": result, "success": True}
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.__class__.__name__} error! {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
