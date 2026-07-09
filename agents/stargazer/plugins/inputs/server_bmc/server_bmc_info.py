# -*- coding: utf-8 -*-
"""Server BMC (Redfish) Information Collector (G5.2 真实现)。

BMC (Baseboard Management Controller) 通过 Redfish REST API 暴露硬件信息。
- 系统信息:`GET /redfish/v1/Systems/{id}`
- 处理器:`GET /redfish/v1/Systems/{id}/Processors`
- 内存:`GET /redfish/v1/Systems/{id}/Memory`
- 电源:`GET /redfish/v1/Chassis/{id}/Power`
- BMC 自身:`GET /redfish/v1/Managers/{id}`

采集字段:型号、序列号、CPU 数量、内存总量、电源状态、BMC 版本。
"""
import logging
import requests

try:
    requests.packages.urllib3.disable_warnings()
except Exception:  # noqa
    pass

logger = logging.getLogger(__name__)


class ServerBmcInfo:
    """采集 server_bmc (Redfish) 实例配置信息 (G5.2 真实现)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("bmc_port", kwargs.get("port", 443)))
        self.user = kwargs.get("user", "admin")
        self.password = kwargs.get("password", "")
        self.ssl = str(kwargs.get("ssl", "true")).lower() in ("1", "true", "yes")
        self.timeout = int(kwargs.get("timeout", 10))
        scheme = "https" if self.ssl else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}"
        self.auth = (self.user, self.password) if self.user else None

    def _get(self, path):
        return requests.get(
            f"{self.base_url}{path}",
            auth=self.auth,
            timeout=self.timeout,
            verify=False,
        )

    def list_all_resources(self):
        """返回标准格式:{"result": {"server_bmc": [model_data]}, "success": True}。"""
        model_data = {
            "ip_addr": self.host,
            "port": self.port,
            "https_enabled": "true" if self.ssl else "false",
        }

        try:
            # 1. 服务根
            try:
                resp = self._get("/redfish/v1/")
                if resp.status_code != 200:
                    model_data["redfish_available"] = False
                    inst_data = {"result": {"server_bmc": [model_data]}, "success": False}
                    return inst_data
                model_data["redfish_available"] = True
                root = resp.json() or {}
                model_data["redfish_version"] = root.get("RedfishVersion", "")
            except Exception:
                model_data["redfish_available"] = False
                inst_data = {"result": {"server_bmc": [model_data]}, "success": False}
                return inst_data

            # 2. 系统信息(取第一个 Systems 集合的第一个成员)
            try:
                sys_resp = self._get("/redfish/v1/Systems")
                if sys_resp.status_code == 200:
                    members = (sys_resp.json() or {}).get("Members", [])
                    if members and isinstance(members, list):
                        sys_id = members[0].get("@odata.id", "").split("/")[-1]
                        if sys_id:
                            detail_resp = self._get(f"/redfish/v1/Systems/{sys_id}")
                            if detail_resp.status_code == 200:
                                sys_data = detail_resp.json() or {}
                                model_data["model"] = sys_data.get("Model", "")
                                model_data["manufacturer"] = sys_data.get("Manufacturer", "")
                                model_data["serial_number"] = sys_data.get("SerialNumber", "")
                                model_data["part_number"] = sys_data.get("PartNumber", "")
                                model_data["uuid"] = sys_data.get("UUID", "")
                                model_data["power_state"] = sys_data.get("PowerState", "")
                                model_data["health"] = sys_data.get("Status", {}).get("Health", "")
                                bios_info = sys_data.get("BiosVersion", "")
                                if bios_info:
                                    model_data["bios_version"] = bios_info
                                proc_summary = sys_data.get("ProcessorSummary", {})
                                if proc_summary:
                                    model_data["cpu_count"] = str(proc_summary.get("Count", ""))
                                    model_data["cpu_model"] = proc_summary.get("Model", "")
                                mem_summary = sys_data.get("MemorySummary", {})
                                if mem_summary:
                                    model_data["memory_total_gib"] = str(
                                        mem_summary.get("TotalSystemMemoryGiB", "")
                                    )
            except Exception:
                pass

            # 3. Manager (BMC 自身信息)
            try:
                mgr_resp = self._get("/redfish/v1/Managers")
                if mgr_resp.status_code == 200:
                    members = (mgr_resp.json() or {}).get("Members", [])
                    if members and isinstance(members, list):
                        mgr_id = members[0].get("@odata.id", "").split("/")[-1]
                        if mgr_id:
                            mgr_detail = self._get(f"/redfish/v1/Managers/{mgr_id}")
                            if mgr_detail.status_code == 200:
                                mgr = mgr_detail.json() or {}
                                model_data["bmc_firmware_version"] = mgr.get("FirmwareVersion", "")
                                model_data["bmc_model"] = mgr.get("Model", "")
            except Exception:
                pass

            inst_data = {"result": {"server_bmc": [model_data]}, "success": True}
        except Exception as err:
            import traceback
            logger.error(f"server_bmc_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data