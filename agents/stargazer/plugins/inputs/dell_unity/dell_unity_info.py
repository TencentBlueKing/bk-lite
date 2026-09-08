# -*- coding: utf-8 -*-
"""Dell Unity 存储采集（Unisphere REST Basic，多对象，Beta）。

对齐官方 Unisphere Management REST（base_path=/api，默认 443 Basic）：
  请求头 X-EMC-REST-CLIENT: true（GET 需要）；
  可选 GET /api/types/loginSessionInfo/instances 取会话 / CSRF；
  GET /api/types/system/instances（回退 /api/instances/system/0）；
  GET /api/types/pool|lun|disk|ethernetPort|fcPort/instances。

字段按官方属性校准，不编造：
  system.serialNumber / model / softwareVersion；
  pool.sizeTotal|sizeUsed|sizeFree；
  lun.wwn + pool.name；
  disk.manufacturer / model / diskTechnology / rawSize / slotNumber / wwn；
  ethernetPort.macAddress；fcPort.wwn（WWPN）。
禁止 storops / NaviCLI / SMI-S。

输出结构：{"result": {"storage":[...], "storage_pool":[...],
          "storage_disk":[...], "storage_volume":[...],
          "storage_eth_port":[...], "storage_fc_port":[...]}, "success": True}
无 MAC / 无 WWPN 原样返回，不编造。
"""
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

try:
    from sanic.log import logger
except ImportError:  # server 侧 mock 映射单测没有 sanic
    import logging

    logger = logging.getLogger("dell_unity")


def _as_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _bytes_to_gb(value):
    try:
        return int(int(float(value)) / (1024**3))
    except (TypeError, ValueError):
        return 0


def _health_value(item):
    health = item.get("health") if isinstance(item, dict) else None
    if isinstance(health, dict):
        return health.get("value")
    return health


def _entry_content(entry):
    if not isinstance(entry, dict):
        return {}
    content = entry.get("content")
    if isinstance(content, dict):
        return content
    return entry


class DellUnityManager:
    """Dell Unity Unisphere REST 配置采集。"""

    PAGE_SIZE = 100
    BASE_PATH = "/api"
    # Unity HealthEnum.OK = 5（Unisphere REST 官方枚举）
    HEALTH_OK = 5

    def __init__(self, params: dict):
        self.host = params.get("host", "")
        self.port = int(params.get("port", 443))
        self.scheme = params.get("scheme", "https") or "https"
        self.username = params.get("username") or params.get("user", "")
        self.password = params.get("password", "")
        self.timeout = 60
        self.verify_tls = _as_bool(params.get("verify_tls", True))
        self.base_url = f"{self.scheme}://{self.host}:{self.port}"
        self.collection_task_id = params.get("collection_task_id")
        self._client: httpx.AsyncClient | None = None
        self._csrf = ""

    def _headers(self):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EMC-REST-CLIENT": "true",
        }
        if self._csrf:
            headers["EMC-CSRF-TOKEN"] = self._csrf
        return headers

    def _auth(self):
        return (self.username, self.password)

    def _abs_url(self, href: str, current_url: str = "") -> str:
        token = _text(href)
        if not token:
            return ""
        if token.startswith("http://") or token.startswith("https://"):
            parsed = urlparse(token)
            return f"{self.scheme}://{self.host}:{self.port}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")
        if token.startswith("?") or token.startswith("&"):
            base = current_url or f"{self.base_url}{self.BASE_PATH}/"
            parsed = urlparse(base)
            extra = dict(parse_qsl(token.lstrip("?&"), keep_blank_values=True))
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query.update(extra)
            return urlunparse((self.scheme, f"{self.host}:{self.port}", parsed.path, "", urlencode(query), ""))
        return urljoin(f"{self.base_url}/", token.lstrip("/"))

    def _capture_csrf(self, resp):
        headers = getattr(resp, "headers", None) or {}
        token = headers.get("EMC-CSRF-TOKEN") or headers.get("emc-csrf-token")
        if token:
            self._csrf = _text(token)
            return
        cookies = getattr(resp, "cookies", None)
        cookie = cookies.get("EMC-CSRF-TOKEN") if cookies is not None else None
        if cookie:
            self._csrf = _text(cookie)

    async def _get_json(self, path, params=None, required=False):
        url = path if str(path).startswith("http") else f"{self.base_url}{self.BASE_PATH}/{str(path).lstrip('/')}"
        try:
            resp = await self._client.get(url, headers=self._headers(), params=params, auth=self._auth())
        except Exception as exc:  # noqa: BLE001
            if required:
                raise
            logger.warning("event=dell_unity_http_failed path=%s error_type=%s", path, type(exc).__name__)
            return {}
        self._capture_csrf(resp)
        if resp.status_code in {401, 403} and required:
            raise RuntimeError("Dell Unity 认证失败")
        if resp.status_code == 404:
            logger.warning("event=dell_unity_endpoint_missing path=%s", path)
            return {}
        if resp.status_code >= 400:
            if required:
                raise RuntimeError(f"Dell Unity 请求失败 status={resp.status_code}")
            logger.warning("event=dell_unity_http_status path=%s status=%s", path, resp.status_code)
            return {}
        try:
            body = resp.json() or {}
        except Exception as exc:  # noqa: BLE001
            if required:
                raise RuntimeError("Dell Unity 响应不是 JSON") from exc
            logger.warning("event=dell_unity_bad_json path=%s error_type=%s", path, type(exc).__name__)
            return {}
        return body if isinstance(body, dict) else {}

    def _next_href(self, body):
        links = body.get("links") or body.get("@links") or []
        if isinstance(links, dict):
            links = [links]
        for item in links:
            if not isinstance(item, dict):
                continue
            if _text(item.get("rel")).lower() == "next":
                return _text(item.get("href"))
        return ""

    async def _fetch_instances(self, type_name, fields, required=False):
        items = []
        params = {"fields": fields, "compact": "true", "per_page": self.PAGE_SIZE, "page": 1}
        url = f"{self.base_url}{self.BASE_PATH}/types/{type_name}/instances"
        query = params
        while url:
            body = await self._get_json(url, params=query, required=required and not items)
            if not body:
                break
            raw_entries = body.get("entries")
            if raw_entries is None and "content" in body:
                raw_entries = [body]
            if not isinstance(raw_entries, list):
                raw_entries = []
            batch = [_entry_content(entry) for entry in raw_entries if isinstance(entry, dict)]
            items.extend(item for item in batch if item)
            next_href = self._next_href(body)
            if not next_href:
                # Unisphere 无 next 即结束；满页也不再自增 page，避免末页循环。
                break
            url = self._abs_url(next_href, url)
            query = None
        return items

    async def _fetch_system(self):
        systems = await self._fetch_instances(
            "system",
            "id,name,model,serialNumber,softwareVersion,health",
            required=True,
        )
        if systems:
            return systems[0]
        body = await self._get_json(
            "instances/system/0",
            params={"fields": "id,name,model,serialNumber,softwareVersion,health", "compact": "true"},
        )
        return _entry_content(body) if body else {}

    @staticmethod
    def _flatten_pool(pool):
        return {
            "name": _text(pool.get("name")),
            "id": _text(pool.get("id")),
            "type": _text(pool.get("type")),
            "sizeTotal": pool.get("sizeTotal") if pool.get("sizeTotal") not in (None, "") else "",
            "sizeUsed": pool.get("sizeUsed") if pool.get("sizeUsed") not in (None, "") else "",
            "sizeFree": pool.get("sizeFree") if pool.get("sizeFree") not in (None, "") else "",
            "health_value": _health_value(pool) if _health_value(pool) not in (None, "") else "",
            "state": "online" if _health_value(pool) == DellUnityManager.HEALTH_OK else "offline",
        }

    @staticmethod
    def _flatten_disk(disk):
        return {
            "name": _text(disk.get("name")),
            "id": _text(disk.get("id")),
            "manufacturer": _text(disk.get("manufacturer")),
            "model": _text(disk.get("model")),
            "diskTechnology": _text(disk.get("diskTechnology")),
            "rawSize": disk.get("rawSize") if disk.get("rawSize") not in (None, "") else "",
            "wwn": _text(disk.get("wwn")),
            "slotNumber": disk.get("slotNumber") if disk.get("slotNumber") not in (None, "") else "",
            "rpm": disk.get("rpm") if disk.get("rpm") not in (None, "") else "",
            "health_value": _health_value(disk) if _health_value(disk) not in (None, "") else "",
            "state": "online" if _health_value(disk) == DellUnityManager.HEALTH_OK else "offline",
        }

    @staticmethod
    def _flatten_lun(lun):
        pool = lun.get("pool") if isinstance(lun.get("pool"), dict) else {}
        return {
            "name": _text(lun.get("name")),
            "id": _text(lun.get("id")),
            "wwn": _text(lun.get("wwn")),
            "sizeTotal": lun.get("sizeTotal") if lun.get("sizeTotal") not in (None, "") else "",
            "sizeAllocated": lun.get("sizeAllocated") if lun.get("sizeAllocated") not in (None, "") else "",
            "type": _text(lun.get("type")),
            "parent_pool": _text(pool.get("name")),
            "health_value": _health_value(lun) if _health_value(lun) not in (None, "") else "",
            "state": "online" if _health_value(lun) == DellUnityManager.HEALTH_OK else "offline",
        }

    @staticmethod
    def _flatten_eth(port):
        processor = port.get("storageProcessor") if isinstance(port.get("storageProcessor"), dict) else {}
        link_up = port.get("isLinkUp")
        return {
            "name": _text(port.get("name")),
            "id": _text(port.get("id")),
            "macAddress": _text(port.get("macAddress")),
            "currentSpeed": port.get("currentSpeed") if port.get("currentSpeed") not in (None, "") else "",
            "isLinkUp": "" if link_up in (None, "") else str(bool(link_up)).lower(),
            "storageProcessor": _text(processor.get("name") or processor.get("id")),
            "health_value": _health_value(port) if _health_value(port) not in (None, "") else "",
            "state": "up" if link_up is True else "down",
        }

    @staticmethod
    def _flatten_fc(port):
        processor = port.get("storageProcessor") if isinstance(port.get("storageProcessor"), dict) else {}
        link_up = port.get("isLinkUp")
        return {
            "name": _text(port.get("name")),
            "id": _text(port.get("id")),
            "wwn": _text(port.get("wwn")),
            "currentSpeed": port.get("currentSpeed") if port.get("currentSpeed") not in (None, "") else "",
            "isLinkUp": "" if link_up in (None, "") else str(bool(link_up)).lower(),
            "storageProcessor": _text(processor.get("name") or processor.get("id")),
            "health_value": _health_value(port) if _health_value(port) not in (None, "") else "",
            "state": "up" if link_up is True else "down",
        }

    async def _optional_login(self):
        await self._get_json("types/loginSessionInfo/instances", params={"compact": "true"})

    async def list_all_resources(self):
        self._client = httpx.AsyncClient(timeout=self.timeout, verify=self.verify_tls)
        try:
            await self._optional_login()
            system = await self._fetch_system()
            if not system:
                raise RuntimeError("Dell Unity 未返回 system")
            pools = await self._fetch_instances("pool", "id,name,sizeTotal,sizeUsed,sizeFree,type,health")
            disks = await self._fetch_instances(
                "disk",
                "id,name,manufacturer,model,diskTechnology,rawSize,wwn,slotNumber,rpm,health",
            )
            luns = await self._fetch_instances("lun", "id,name,wwn,sizeTotal,sizeAllocated,type,pool.name,health")
            eth_ports = await self._fetch_instances(
                "ethernetPort",
                "id,name,macAddress,currentSpeed,isLinkUp,health,storageProcessor.name",
            )
            fc_ports = await self._fetch_instances(
                "fcPort",
                "id,name,wwn,currentSpeed,isLinkUp,health,storageProcessor.name",
            )

            flat_pools = [self._flatten_pool(item) for item in pools]
            flat_disks = [self._flatten_disk(item) for item in disks]
            flat_luns = [self._flatten_lun(item) for item in luns]
            flat_eth = [self._flatten_eth(item) for item in eth_ports]
            flat_fc = [self._flatten_fc(item) for item in fc_ports]

            total = used = avail = 0
            for pool in flat_pools:
                total += _bytes_to_gb(pool.get("sizeTotal"))
                used += _bytes_to_gb(pool.get("sizeUsed"))
                avail += _bytes_to_gb(pool.get("sizeFree"))

            storage = {
                "device_sn": _text(system.get("serialNumber") or system.get("id")),
                "ip_addr": self.host,
                "model": _text(system.get("model")),
                "brand": "dell",
                "storage_type": "SAN",
                "firmware_version": _text(system.get("softwareVersion")),
                "sys_desc": _text(system.get("name")) or "Dell Unity",
                "total_capacity": str(total),
                "used_capacity": str(used),
                "available_capacity": str(avail),
                "pool_count": str(len(flat_pools)),
                "disk_count": str(len(flat_disks)),
                "volume_count": str(len(flat_luns)),
                "state": "online" if _health_value(system) == self.HEALTH_OK else "offline",
            }
            return {
                "result": {
                    "storage": [storage],
                    "storage_pool": flat_pools,
                    "storage_disk": flat_disks,
                    "storage_volume": flat_luns,
                    "storage_eth_port": flat_eth,
                    "storage_fc_port": flat_fc,
                },
                "success": True,
            }
        except Exception as err:  # noqa
            logger.exception(
                "event=dell_unity_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
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
