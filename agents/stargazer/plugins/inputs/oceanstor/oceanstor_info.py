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
import httpx
from sanic.log import logger


class OceanStorManager:
    """华为 OceanStor 配置采集。"""

    PAGE_SIZE = 100

    def __init__(self, params: dict):
        self.host = params.get("host", "")
        self.port = int(params.get("port", 8088))
        self.scheme = params.get("scheme", "https") or "https"
        self.username = params.get("username") or params.get("user", "")
        self.password = params.get("password", "")
        self.timeout = 60  # 请求超时硬编码；表单 timeout 由框架作单对象预算
        raw_verify_tls = params.get("verify_tls", True)
        self.verify_tls = raw_verify_tls if isinstance(raw_verify_tls, bool) else str(raw_verify_tls).strip().lower() in {"1", "true", "yes", "on"}
        self.base_url = f"{self.scheme}://{self.host}:{self.port}"
        self.token = None
        self.device_id = None
        self._client: httpx.AsyncClient | None = None
        self.collection_task_id = params.get("collection_task_id")

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["iBaseToken"] = self.token
        return h

    async def login(self):
        url = f"{self.base_url}/deviceManager/rest/xxxxx/sessions"
        payload = {"username": self.username, "password": self.password, "scope": "0"}
        resp = await self._client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        data = (resp.json() or {}).get("data", {})
        if not data:
            raise RuntimeError("OceanStor 登录失败：未返回 data")
        self.token = data.get("iBaseToken")
        self.device_id = data.get("deviceid")
        if not self.token or not self.device_id:
            raise RuntimeError("OceanStor 登录失败：缺少 iBaseToken/deviceid")

    async def logout(self):
        if not self.device_id or self._client is None:
            return
        try:
            url = f"{self.base_url}/deviceManager/rest/{self.device_id}/sessions"
            await self._client.delete(url, headers=self._headers())
        except Exception as e:  # noqa
            logger.warning(f"OceanStor logout error: {e}")

    async def _fetch_all(self, path):
        """分页拉取某配置端点的全部对象。"""
        url = f"{self.base_url}/deviceManager/rest/{self.device_id}/{path}"
        items, start = [], 0
        while True:
            params = {"range": f"[{start}-{start + self.PAGE_SIZE - 1}]"}
            resp = await self._client.get(url, headers=self._headers(), params=params)
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

    async def list_all_resources(self):
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            verify=self.verify_tls,
        )
        try:
            await self.login()
            pools = await self._fetch_all("storagepool")
            disks = await self._fetch_all("disk")
            luns = await self._fetch_all("lun")

            def _gb(sectors, sector_size):
                try:
                    return int(int(float(sectors)) * int(float(sector_size)) / (1024**3))
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
                "model": "",
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
                "storage_pool": pools,
                "storage_disk": disks,
                "storage_volume": luns,
            }
            return {"result": result, "success": True}
        except Exception as err:  # noqa
            logger.exception(
                "event=oceanstor_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                self.host,
                self.collection_task_id,
                "list_all_resources",
                type(err).__name__,
            )
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}
        finally:
            await self.logout()
            if self._client is not None:
                await self._client.aclose()
                self._client = None
