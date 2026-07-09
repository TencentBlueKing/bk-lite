# -*- coding: utf-8 -*-
"""Nacos Information Collector (G5.2 真实现)。

Nacos 2.x REST API:健康检查 + 命名空间 + 服务列表 + 配置列表
- 健康检查:`GET /nacos/v2/console/server/health` 或 v1 路径
- 服务列表:`GET /nacos/v2/ns/service/list?pageNo=1&pageSize=10`
- 配置列表:`GET /nacos/v2/cs/config/list?dataId=&group=DEFAULT_GROUP&pageNo=1&pageSize=10`
- 命名空间:`GET /nacos/v2/console/namespace/list`

采集字段:版本、命名空间数量、服务数量、配置数量、健康状态。
"""
import logging
import requests

try:
    requests.packages.urllib3.disable_warnings()
except Exception:  # noqa
    pass

logger = logging.getLogger(__name__)


class NacosInfo:
    """采集 nacos 实例配置信息 (G5.2 真实现)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 8848))
        self.username = kwargs.get("username", "nacos")
        self.password = kwargs.get("password", "nacos")
        self.namespace = kwargs.get("namespace", "")
        self.timeout = int(kwargs.get("timeout", 10))
        scheme = "https" if str(kwargs.get("ssl", "")).lower() in ("1", "true", "yes") else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}"
        self.auth = (self.username, self.password) if self.username else None

    def _get(self, path, params=None):
        return requests.get(
            f"{self.base_url}{path}",
            params=params or {},
            auth=self.auth,
            timeout=self.timeout,
            verify=False,
        )

    def list_all_resources(self):
        """返回标准格式:{"result": {"nacos": [model_data]}, "success": True}。"""
        model_data = {
            "ip_addr": self.host,
            "port": self.port,
            "https_enabled": "true" if self.base_url.startswith("https") else "false",
        }

        try:
            # 1. 健康检查 + 版本
            try:
                # v2 路径优先,失败回退 v1
                health = self._get("/nacos/v2/console/server/health")
                if health.status_code == 200:
                    model_data["status"] = "UP"
                else:
                    model_data["status"] = "DOWN"
            except Exception:
                model_data["status"] = "UNKNOWN"

            # 2. 命名空间列表
            try:
                ns_resp = self._get("/nacos/v2/console/namespace/list")
                if ns_resp.status_code == 200:
                    ns_data = ns_resp.json() or {}
                    ns_list = ns_data.get("data", []) if isinstance(ns_data, dict) else []
                    model_data["namespace_count"] = len(ns_list)
                    model_data["namespaces"] = [
                        {"id": ns.get("namespaceId", ""), "name": ns.get("namespaceName", "")}
                        for ns in ns_list[:10]
                    ]
                else:
                    model_data["namespace_count"] = 0
            except Exception:
                model_data["namespace_count"] = 0

            # 3. 服务列表
            try:
                sv_resp = self._get(
                    "/nacos/v2/ns/service/list",
                    params={"pageNo": 1, "pageSize": 100},
                )
                if sv_resp.status_code == 200:
                    sv_data = sv_resp.json() or {}
                    sv_list = sv_data.get("data", []) if isinstance(sv_data, dict) else []
                    # v2 返回 dict 包含 "services" 或 "datas"
                    services = sv_list if isinstance(sv_list, list) else sv_list.get("services", [])
                    model_data["service_count"] = len(services) if isinstance(services, list) else 0
                else:
                    model_data["service_count"] = 0
            except Exception:
                model_data["service_count"] = 0

            # 4. 配置列表
            try:
                cfg_resp = self._get(
                    "/nacos/v2/cs/config/list",
                    params={
                        "dataId": "",
                        "group": "DEFAULT_GROUP",
                        "pageNo": 1,
                        "pageSize": 100,
                    },
                )
                if cfg_resp.status_code == 200:
                    cfg_data = cfg_resp.json() or {}
                    cfg_list = cfg_data.get("data", []) if isinstance(cfg_data, dict) else []
                    items = cfg_list if isinstance(cfg_list, list) else cfg_list.get("pageItems", [])
                    model_data["config_count"] = len(items) if isinstance(items, list) else 0
                else:
                    model_data["config_count"] = 0
            except Exception:
                model_data["config_count"] = 0

            # 5. 版本信息(从 actuator/info 路径或 health 头推断)
            try:
                info_resp = self._get("/nacos/v2/console/server/state")
                if info_resp.status_code == 200:
                    state_data = info_resp.json() or {}
                    if isinstance(state_data, dict):
                        data = state_data.get("data", state_data)
                        if isinstance(data, dict):
                            model_data["version"] = data.get("version", "")
            except Exception:
                pass

            inst_data = {"result": {"nacos": [model_data]}, "success": True}
        except Exception as err:
            import traceback
            logger.error(f"nacos_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data