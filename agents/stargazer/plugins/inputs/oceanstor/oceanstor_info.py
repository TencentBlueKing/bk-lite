# -*- coding: utf-8 -*-
"""华为 OceanStor 存储采集（DeviceManager REST，多对象，Beta）。

复用监控侧调用契约（已与官方《Dorado 6.1.8 REST 接口参考》校验一致）：
  登录 POST /deviceManager/rest/xxxxx/sessions（scope=0）→ iBaseToken + deviceid；
  配置端点 GET /storagepool、/disk、/lun（仅取配置，不取性能）；
  分页 range=[start-end]；登出 DELETE /sessions。

输出结构：{"result": {"storage":[...], "storage_pool":[...],
          "storage_disk":[...], "storage_volume":[...]}, "success": True}
子对象字段保留 OceanStor 原始字段名（NAME/USERTOTALCAPACITY/SECTORSIZE/LOCATION/
MODEL/SERIALNUMBER/DISKTYPE/SECTORS/SPEEDRPM/MANUFACTURER/WWN/CAPACITY/ALLOCCAPACITY/
ALLOCTYPE/PARENTNAME/USAGETYPE/RUNNINGSTATUS），由 CMDB 侧 runner 归一化。
"""
import requests
from sanic.log import logger

try:
    requests.packages.urllib3.disable_warnings()
except Exception:  # noqa
    pass


class OceanStorManager:
    """华为 OceanStor 配置采集。"""

    PAGE_SIZE = 100

    def __init__(self, params: dict):
        self.host = params.get("host", "")
        self.port = int(params.get("port", 8088))
        self.username = params.get("username") or params.get("user", "")
        self.password = params.get("password", "")
        self.timeout = int(params.get("timeout", 60))
        self.base_url = f"https://{self.host}:{self.port}"
        self.token = None
        self.device_id = None

    # ------------------------------------------------------------------
    # 会话
    # ------------------------------------------------------------------
    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["iBaseToken"] = self.token
        return h

    def login(self):
        url = f"{self.base_url}/deviceManager/rest/xxxxx/sessions"
        payload = {"username": self.username, "password": self.password, "scope": "0"}
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"},
                             verify=False, timeout=self.timeout)
        data = (resp.json() or {}).get("data", {})
        if not data:
            raise RuntimeError("OceanStor 登录失败：未返回 data")
        self.token = data.get("iBaseToken")
        self.device_id = data.get("deviceid")
        if not self.token or not self.device_id:
            raise RuntimeError("OceanStor 登录失败：缺少 iBaseToken/deviceid")

    def logout(self):
        if not self.device_id:
            return
        try:
            url = f"{self.base_url}/deviceManager/rest/{self.device_id}/sessions"
            requests.delete(url, headers=self._headers(), verify=False, timeout=self.timeout)
        except Exception as e:  # noqa
            logger.warning(f"OceanStor logout error: {e}")

    def _fetch_all(self, path):
        """分页拉取某配置端点的全部对象。"""
        url = f"{self.base_url}/deviceManager/rest/{self.device_id}/{path}"
        items, start = [], 0
        while True:
            params = {"range": f"[{start}-{start + self.PAGE_SIZE - 1}]"}
            resp = requests.get(url, headers=self._headers(), params=params,
                                verify=False, timeout=self.timeout)
            body = resp.json() or {}
            if (body.get("error") or {}).get("code", 0) != 0:
                logger.warning(f"OceanStor fetch {path} error: {body.get('error')}")
                break
            batch = body.get("data", []) or []
            items.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
            start += self.PAGE_SIZE
        return items

    # ------------------------------------------------------------------
    # 采集入口
    # ------------------------------------------------------------------
    def list_all_resources(self):
        try:
            self.login()
            pools = self._fetch_all("storagepool")
            disks = self._fetch_all("disk")
            luns = self._fetch_all("lun")

            # 主对象：设备级字段 + 聚合数量（容量由各池汇总，单位 GB）
            def _gb(sectors, sector_size):
                try:
                    return int(int(float(sectors)) * int(float(sector_size)) / (1024 ** 3))
                except (TypeError, ValueError):
                    return 0

            total = used = avail = 0
            for p in pools:
                ss = p.get("SECTORSIZE", "512")
                total += _gb(p.get("USERTOTALCAPACITY", 0), ss)
                used += _gb(p.get("USERCONSUMEDCAPACITY", 0), ss)
                avail += _gb(p.get("USERFREECAPACITY", 0), ss)

            storage = {
                "device_sn": self.device_id,
                "model": "",          # 可由 /system 端点补充
                "brand": "huawei",
                "storage_type": "SAN",
                "firmware_version": "",
                "sys_desc": "Huawei OceanStor",
                "total_capacity": str(total),
                "used_capacity": str(used),
                "available_capacity": str(avail),
                "pool_count": str(len(pools)),
                "disk_count": str(len(disks)),
                "volume_count": str(len(luns)),
                "RUNNINGSTATUS": "27",
            }

            result = {
                "storage": [storage],
                "storage_pool": pools,      # 原始 OceanStor 字段，CMDB runner 归一化
                "storage_disk": disks,
                "storage_volume": luns,
            }
            inst_data = {"result": result, "success": True}
        except Exception as err:  # noqa
            import traceback
            logger.error(f"oceanstor_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}
        finally:
            self.logout()

        return inst_data
