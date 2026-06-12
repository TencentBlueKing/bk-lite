# -*- coding: utf-8 -*-
"""OpenStack 采集器：自包含 Keystone v3 REST 实现（requests，不依赖 novaclient 等 SDK）。

移植自 old_plugins/.../resource_apis/cw_openstackcloud.py，保留其 HTTP/认证/
list_scoped_project/handle_* 逻辑（经过验证），仅去掉 old 框架依赖
（cmp.cloud_apis.*、core.logger、PrivateCloudManage、@register），并把 handle_*
原始输出重命名为 CMDB 模型 attr 字段 + 关联用隐藏字段。

输出结构：{"result": {"openstack":[...], "openstack_node":[...], "openstack_vm":[...],
"openstack_vg":[...], "openstack_sp":[...]}, "success": bool}
"""
import json
import traceback

from sanic.log import logger

# `requests` 仅在真正发起 HTTP 时才需要；延迟导入，保证模块（含纯函数与字段重命名）
# 在未安装 requests 的精简环境下也可导入与单测。
try:  # pragma: no cover - 取决于运行环境是否装了 requests
    import requests
except ImportError:  # pragma: no cover
    requests = None


# openstack api 接口枚举（端口与路径与 old get_resource_uri 完全一致）
def get_resource_uri(op, basic_url, **kwargs):
    return (
        {
            # Identity
            "auth_token": "{basic_url}:5000/v3/auth/tokens",
            "list_projects": "{basic_url}:5000/v3/projects",
            # Compute
            "list_nodes": "{basic_url}:8774/v2.1/os-hypervisors/detail",
            "list_vms": "{basic_url}:8774/v2.1/servers/detail",
            "get_flavor": "{basic_url}:8774/v2.1/flavors/{flavor_id}",
            # Volume
            "list_volumes": "{basic_url}:8776/v3/{project_id}/volumes/detail",
            "list_sps": "{basic_url}:8776/v3/{project_id}/scheduler-stats/get_pools?detail=true",
        }
        .get(op, "")
        .format(basic_url=basic_url, **kwargs)
    )


def handle_request(method, url, **kwargs):
    if requests is None:
        raise RuntimeError(
            "OpenStack 采集需要 requests 库，但当前运行环境未安装 requests，请在 stargazer 运行环境安装后重试"
        )
    try:
        resp = requests.request(method, url, **kwargs)
    except Exception:
        logger.exception(f"openstack 请求失败,url:{url},method:{method}")
        return {"result": False, "message": f"请求失败,url:{url},method:{method}", "data": {}}
    if resp.status_code > 300:
        logger.error(
            f"openstack 请求失败,url:{url},method:{method},"
            f"status_code:{resp.status_code},message:{resp.content.decode('utf-8')}"
        )
        return {
            "result": False,
            "message": f"请求错误,status_code:{resp.status_code},message:{resp.content.decode('utf-8')}",
            "data": {},
        }
    logger.info(f"openstack 请求成功,url:{url},method:{method}")
    return {"result": True, "data": resp.json()}


class OpenStackManager:
    """OpenStack 私有云采集器。自包含 Keystone v3 认证 + 资源拉取。"""

    VM_POWER_STATE = {
        "0": "无状态",
        "1": "运行中",
        "3": "已暂停",
        "4": "关机",
        "6": "已崩溃",
        "7": "已挂起",
    }

    VOLUME_STATE = {
        "CREATING": "创建中",
        "AVAILABLE": "可用",
        "RESERVED": "已预留",
        "ATTACHING": "附加中",
        "DETACHING": "分离中",
        "IN-USE": "使用中",
        "MAINTENANCE": "维护中",
        "DELETING": "删除中",
        "AWAITING-TRANSFER": "等待传输",
        "ERROR": "错误",
        "ERROR_DELETING": "删除错误",
        "BACKING-UP": "备份中",
        "RESTORING-BACKUP": "恢复备份中",
        "ERROR_BACKING-UP": "备份错误",
        "ERROR_RESTORING": "恢复错误",
        "ERROR_EXTENDING": "扩展错误",
        "DOWNLOADING": "下载中",
        "UPLOADING": "上传中",
        "RETYPING": "重新键入中",
        "EXTENDING": "扩展中",
    }

    def __init__(self, params: dict):
        self.params = params or {}
        self.account = self.params.get("username") or self.params.get("accessKey")
        self.password = self.params.get("password") or self.params.get("accessSecret")
        self.region = self.params.get("region", "") or ""
        self.host = self.params.get("host", "") or ""
        self.scheme = self.params.get("scheme", "http") or "http"
        self.user_domain_name = self.params.get("user_domain_name", "Default") or "Default"
        self.version = self.params.get("version", "v3") or "v3"
        self.project_id = self.params.get("project_id", "")
        self.basic_url = f"{self.scheme}://{self.host}"
        self.cw_headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json",
        }
        self._handle_request = handle_request
        self._auth_token = None

    # ----------------------------------------------------------------------
    # 认证（移植 old login，逻辑保持不变）
    # ----------------------------------------------------------------------
    def login(self):
        if requests is None:
            raise RuntimeError(
                "OpenStack 采集需要 requests 库，但当前运行环境未安装 requests，请在 stargazer 运行环境安装后重试"
            )
        params = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.account,
                            "domain": {"name": self.user_domain_name},
                            "password": self.password,
                        }
                    },
                },
                "scope": {"system": {"all": True}},
            }
        }
        json_data = json.dumps(params)
        url = get_resource_uri("auth_token", self.basic_url)
        response = requests.post(url, data=json_data, headers=self.cw_headers)
        if response.status_code == 201:
            token_ = response.headers["X-Subject-Token"]
            catalog_list = response.json().get("token", {}).get("catalog", [{"endpoints": [{"region": ""}]}])
            if self.region == "" or self.region is None:
                for item in catalog_list:
                    if "endpoints" not in item:
                        continue
                    endpoints = item.get("endpoints")
                    if len(endpoints) == 0:
                        continue
                    for endpoint in endpoints:
                        if "region" in endpoint:
                            self.region = endpoint.get("region")
                            return token_
            return token_
        return None

    def _ensure_auth(self):
        if not self._auth_token:
            self._auth_token = self.login()
            self.cw_headers.update({"X-Auth-Token": self._auth_token, "Accept-Charset": "utf-8;q=1"})
        return self._auth_token

    def get_query_params(self):
        return {"headers": self.cw_headers, "verify": False}

    # ----------------------------------------------------------------------
    # handle_*（移植 old，返回原始资源字段；签名简化为单返回值）
    # ----------------------------------------------------------------------
    def handle_node(self, item, project_id=None):
        return {
            key: str(item[key])
            for key in item
            if key in ["hypervisor_hostname", "id", "memory_mb", "vcpus", "local_gb", "host_ip"]
        }

    def handle_vm(self, item, project_id, dict_flavor):
        item_ = {
            "hostname": item.get("name", ""),
            "id": item.get("id", ""),
            "power_state": self.VM_POWER_STATE.get(str(item.get("OS-EXT-STS:power_state", "")), ""),
            "zone": item.get("OS-EXT-AZ:availability_zone", ""),
            "node_name": item.get("OS-EXT-SRV-ATTR:host", ""),
            "region": self.region,
            "project_id": item.get("tenant_id", ""),
        }
        dict_ = item.get("flavor", {"id": None})
        flavor_id = dict_.get("id", None)
        if flavor_id is not None:
            if flavor_id in dict_flavor:
                dict_ = dict_flavor.get(flavor_id, {})
            else:
                url = get_resource_uri("get_flavor", self.basic_url, flavor_id=flavor_id)
                flavor_resp = self._handle_request("GET", url, **self.get_query_params()).get("data") or {}
                dict_ = flavor_resp.get("flavor", {})
                dict_flavor.setdefault(flavor_id, dict_)
            item_["ram"] = dict_.get("ram", None)
            item_["vcpus"] = dict_.get("vcpus", None)
            item_["disk"] = dict_.get("disk", None)
        dict_ = item.get("addresses", {"public": [{"addr": ""}]})
        if not dict_:
            dict_ = [{"addr": ""}]
        else:
            dict_ = next(iter(dict_.values()))
        item_["addresses"] = dict_[0].get("addr", "")
        return item_, dict_flavor

    def handle_volume(self, item, project_id):
        status = item.get("status", "").upper()
        status_cn = self.VOLUME_STATE.get(status, None)
        vm_id = ""
        for attach in item.get("attachments", []):
            vm_id = attach.get("server_id", "")
        return {
            "name": item.get("name", ""),
            "id": item.get("id", ""),
            "size": item.get("size", ""),
            "zone": item.get("availability_zone", ""),
            "region": self.region,
            "project_id": project_id,
            "node_name": item.get("os-vol-host-attr:host", "").split("@")[0],
            "status": status_cn,
            "vm_id": vm_id,
            "sp_id": item.get("os-vol-host-attr:host", ""),
        }

    def handle_sp(self, item, project_id):
        capabilities = item.get("capabilities", {})
        return {
            "id": item.get("name", ""),
            "node_name": item.get("name", "").split("@")[0],
            "volume_backend_name": capabilities.get("volume_backend_name", ""),
            "total_capacity_gb": capabilities.get("total_capacity_gb", ""),
            "storage_protocol": capabilities.get("storage_protocol", ""),
            "driver_version": capabilities.get("driver_version", ""),
            "project_id": project_id,
            "region": self.region,
        }

    # ----------------------------------------------------------------------
    # list_scoped_project（移植 old，遍历 projects→取 project token→拉资源→逐条 handle）
    # ----------------------------------------------------------------------
    def list_scoped_project(self, url_, method_, key, dict_):
        self._ensure_auth()
        url = get_resource_uri("list_projects", self.basic_url)
        resp = self._handle_request("GET", url, **self.get_query_params())
        if not resp["result"]:
            return resp

        filter_ = []
        result = resp["data"].get("projects", [])
        for item in result:
            project_id = item.get("id", "")
            project_name = item.get("name", "")
            domain_id = item.get("domain_id", "")

            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json",
            }
            json_data = json.dumps(
                {
                    "auth": {
                        "identity": {
                            "methods": ["password"],
                            "password": {
                                "user": {
                                    "name": self.account,
                                    "domain": {"name": self.user_domain_name},
                                    "password": self.password,
                                }
                            },
                        },
                        "scope": {"project": {"domain": {"id": domain_id}, "name": project_name}},
                    }
                }
            )
            url = get_resource_uri("auth_token", self.basic_url)
            response = requests.post(url, data=json_data, headers=headers)
            if response.status_code == 201:
                headers.update({"X-Auth-Token": response.headers["X-Subject-Token"], "Accept-Charset": "utf-8;q=1"})
            else:
                continue

            url = get_resource_uri(url_, self.basic_url, project_id=project_id)
            response = self._handle_request("GET", url, **{"headers": headers, "verify": False})
            if not response["result"]:
                continue

            result_ = response["data"].get(key, [])
            for item_ in result_:
                method = getattr(self, method_)
                if method_ == "handle_vm":
                    handle_, dict_ = method(item_, project_id, dict_)
                else:
                    handle_ = method(item_, project_id)
                filter_.append(handle_)

        return {"result": True, "data": filter_}

    # 原始 handle_ 列表拉取（与 old list_nodes/list_vms/list_vg/list_sp 对应）
    def list_nodes(self):
        return self.list_scoped_project("list_nodes", "handle_node", "hypervisors", None)

    def list_vms(self):
        return self.list_scoped_project("list_vms", "handle_vm", "servers", {})

    def list_vg(self):
        return self.list_scoped_project("list_volumes", "handle_volume", "volumes", None)

    def list_sp(self):
        return self.list_scoped_project("list_sps", "handle_sp", "pools", None)

    # ----------------------------------------------------------------------
    # 字段重命名纯函数（handle_ 原始字段 → 模型 attr 字段 + 隐藏关联字段）
    # ----------------------------------------------------------------------
    @staticmethod
    def _map_node(raw: dict) -> dict:
        return {
            "resource_name": raw.get("hypervisor_hostname", ""),
            "resource_id": raw.get("id", ""),
            "ip_addr": raw.get("host_ip", ""),
            "ram_mb": raw.get("memory_mb", ""),
            "vcpus": raw.get("vcpus", ""),
            "disk_gb": raw.get("local_gb", ""),
        }

    @staticmethod
    def _map_vm(raw: dict) -> dict:
        return {
            "resource_name": raw.get("hostname", ""),
            "resource_id": raw.get("id", ""),
            "ip_addr": raw.get("addresses", ""),
            "ram_mb": raw.get("ram", ""),
            "vcpus": raw.get("vcpus", ""),
            "disk_gb": raw.get("disk", ""),
            "status": raw.get("power_state", ""),
            "os_name": "",  # 已知缺口：old 插件未产出操作系统名
            "zone": raw.get("zone", ""),
            "region": raw.get("region", ""),
            "project_name": raw.get("project_id", ""),
            # 隐藏关联字段：建 vm→node 关联
            "node_name": raw.get("node_name", ""),
        }

    @staticmethod
    def _map_vg(raw: dict) -> dict:
        return {
            "resource_name": raw.get("name", ""),
            "resource_id": raw.get("id", ""),
            "size_gb": raw.get("size", ""),
            "zone": raw.get("zone", ""),
            "region": raw.get("region", ""),
            "project_name": raw.get("project_id", ""),
            "status": raw.get("status", ""),
            # 隐藏关联字段
            "node_name": raw.get("node_name", ""),
            "vm_id": raw.get("vm_id", ""),
            "sp_id": raw.get("sp_id", ""),
        }

    @staticmethod
    def _map_sp(raw: dict) -> dict:
        return {
            "resource_name": raw.get("volume_backend_name", ""),
            "resource_id": raw.get("id", ""),
            "size_gb": raw.get("total_capacity_gb", ""),
            "region": raw.get("region", ""),
            "project_name": raw.get("project_id", ""),
            "storage_protocol": raw.get("storage_protocol", ""),
            "driver_version": raw.get("driver_version", ""),
            # 隐藏关联字段
            "node_name": raw.get("node_name", ""),
        }

    # ----------------------------------------------------------------------
    # get_*：拉原始列表 + 重命名
    # ----------------------------------------------------------------------
    @staticmethod
    def _unwrap(resp):
        if not resp or not resp.get("result"):
            raise RuntimeError(resp.get("message") if isinstance(resp, dict) else "openstack collect failed")
        return resp.get("data", []) or []

    def get_platform(self):
        """平台对象（openstack）：字段对齐 attr-openstack（global_domain_name）。"""
        return [{"global_domain_name": self.host}]

    def get_nodes(self):
        return [self._map_node(raw) for raw in self._unwrap(self.list_nodes())]

    def get_vms(self):
        return [self._map_vm(raw) for raw in self._unwrap(self.list_vms())]

    def get_vg(self):
        return [self._map_vg(raw) for raw in self._unwrap(self.list_vg())]

    def get_sp(self):
        return [self._map_sp(raw) for raw in self._unwrap(self.list_sp())]

    def exec_script(self):
        return {
            "openstack": self.get_platform(),
            "openstack_node": self.get_nodes(),
            "openstack_vm": self.get_vms(),
            "openstack_vg": self.get_vg(),
            "openstack_sp": self.get_sp(),
        }

    def list_all_resources(self):
        try:
            result = self.exec_script()
            return {"result": result, "success": True}
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.__class__.__name__} error! {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
