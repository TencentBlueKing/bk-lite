# -*- coding: utf-8 -*-
"""NetApp ONTAP 存储采集（REST Basic，多对象，Beta）。

对齐官方 ONTAP REST（base_path=/api，默认 443 Basic）：
  GET /api/cluster（可选 /api/cluster/nodes）；
  GET /api/network/ethernet/ports（mac_address）；
  GET /api/network/fc/ports（wwpn，稳定 REST，未授权/404 视为无 FC）；
  GET /api/storage/aggregates、/storage/disks、/storage/luns、/storage/volumes；
  可选 GET /api/network/ip/interfaces 仅回填以太口 IPv4，不建 LIF 模型。

输出结构：{"result": {"storage":[...], "storage_pool":[...],
          "storage_disk":[...], "storage_volume":[...],
          "storage_eth_port":[...], "storage_fc_port":[...]}, "success": True}
子对象保留 ONTAP 扁平字段（name/mac_address/wwpn/serial_number 等），
由 CMDB 侧 runner 归一化。无 MAC / 无 WWPN 原样返回，不编造。
ONTAP LUN REST 无稳定 wwn/naa 字段时不把 serial_number 当成 WWN。
"""
from urllib.parse import urljoin, urlparse

import httpx

try:
    from sanic.log import logger
except ImportError:  # server 侧 mock 映射单测没有 sanic
    import logging

    logger = logging.getLogger("netapp_ontap")


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


def _nested(data, *keys):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _bytes_to_gb(value):
    try:
        return int(int(float(value)) / (1024**3))
    except (TypeError, ValueError):
        return 0


class NetAppOntapManager:
    """NetApp ONTAP 配置采集。"""

    PAGE_SIZE = 100
    BASE_PATH = "/api"

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

    def _headers(self):
        return {"Accept": "application/json"}

    def _auth(self):
        return (self.username, self.password)

    def _abs_url(self, href: str) -> str:
        token = _text(href)
        if not token:
            return ""
        if token.startswith("http://") or token.startswith("https://"):
            parsed = urlparse(token)
            return f"{self.scheme}://{self.host}:{self.port}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")
        return urljoin(f"{self.base_url}/", token.lstrip("/"))

    async def _get_json(self, path, params=None, required=False):
        url = path if str(path).startswith("http") else f"{self.base_url}{self.BASE_PATH}/{path.lstrip('/')}"
        try:
            resp = await self._client.get(url, headers=self._headers(), params=params, auth=self._auth())
        except Exception as exc:  # noqa: BLE001
            if required:
                raise
            logger.warning("event=netapp_ontap_http_failed path=%s error_type=%s", path, type(exc).__name__)
            return {}
        if resp.status_code in {401, 403} and required:
            raise RuntimeError("NetApp ONTAP 认证失败")
        if resp.status_code == 404:
            logger.warning("event=netapp_ontap_endpoint_missing path=%s", path)
            return {}
        if resp.status_code >= 400:
            if required:
                raise RuntimeError(f"NetApp ONTAP 请求失败 status={resp.status_code}")
            logger.warning("event=netapp_ontap_http_status path=%s status=%s", path, resp.status_code)
            return {}
        try:
            body = resp.json() or {}
        except Exception as exc:  # noqa: BLE001
            if required:
                raise RuntimeError("NetApp ONTAP 响应不是 JSON") from exc
            logger.warning("event=netapp_ontap_bad_json path=%s error_type=%s", path, type(exc).__name__)
            return {}
        return body if isinstance(body, dict) else {}

    async def _fetch_records(self, path, fields=None, required=False):
        items = []
        params = {"max_records": self.PAGE_SIZE}
        if fields:
            params["fields"] = fields
        url = f"{self.base_url}{self.BASE_PATH}/{path.lstrip('/')}"
        query = params
        while url:
            body = await self._get_json(url, params=query, required=required and not items)
            if not body:
                break
            batch = body.get("records") or []
            if isinstance(batch, dict):
                batch = [batch]
            if not isinstance(batch, list):
                batch = []
            items.extend(item for item in batch if isinstance(item, dict))
            next_href = _nested(body, "_links", "next", "href")
            url = self._abs_url(next_href) if next_href else ""
            query = None
            if len(batch) < self.PAGE_SIZE and not next_href:
                break
        return items

    @staticmethod
    def _cluster_firmware(cluster):
        version = cluster.get("version")
        if isinstance(version, dict):
            return _text(version.get("full"))
        return _text(version)

    @staticmethod
    def _first_node_field(nodes, *keys):
        if not nodes:
            return ""
        node = nodes[0] if isinstance(nodes[0], dict) else {}
        for key in keys:
            value = _text(node.get(key))
            if value:
                return value
        return ""

    @staticmethod
    def _space_gb(space, *keys):
        if not isinstance(space, dict):
            return 0
        current = space
        for key in keys:
            if not isinstance(current, dict):
                return _bytes_to_gb(current)
            current = current.get(key)
        return _bytes_to_gb(current)

    @staticmethod
    def _volume_wwn(item):
        for key in ("wwn", "naa", "wwid"):
            value = _text(item.get(key))
            if value:
                return value
        scsi = item.get("scsi")
        if isinstance(scsi, dict):
            for key in ("naa", "wwn", "wwid"):
                value = _text(scsi.get(key))
                if value:
                    return value
        return ""

    @staticmethod
    def _flatten_eth(port, ip_by_port):
        node = port.get("node") if isinstance(port.get("node"), dict) else {}
        name = _text(port.get("name"))
        node_name = _text(node.get("name"))
        return {
            "name": name,
            "mac_address": _text(port.get("mac_address")),
            "state": _text(port.get("state")),
            "speed": port.get("speed") if port.get("speed") not in (None, "") else "",
            "node_name": node_name,
            "uuid": _text(port.get("uuid")),
            "ip_addr": ip_by_port.get((name, node_name)) or ip_by_port.get((name, "")) or "",
        }

    @staticmethod
    def _flatten_fc(port):
        node = port.get("node") if isinstance(port.get("node"), dict) else {}
        speed = port.get("speed")
        operating = _nested(speed, "operating") if isinstance(speed, dict) else speed
        return {
            "name": _text(port.get("name")),
            "wwpn": _text(port.get("wwpn")),
            "wwnn": _text(port.get("wwnn")),
            "state": _text(port.get("state")),
            "speed": _text(operating),
            "node_name": _text(node.get("name")),
            "uuid": _text(port.get("uuid")),
        }

    @staticmethod
    def _flatten_pool(pool):
        space = pool.get("space") if isinstance(pool.get("space"), dict) else {}
        block = space.get("block_storage") if isinstance(space.get("block_storage"), dict) else space
        return {
            "name": _text(pool.get("name")),
            "uuid": _text(pool.get("uuid")),
            "state": _text(pool.get("state")),
            "total_bytes": block.get("size") if block.get("size") not in (None, "") else "",
            "used_bytes": block.get("used") if block.get("used") not in (None, "") else "",
            "available_bytes": block.get("available") if block.get("available") not in (None, "") else "",
        }

    @staticmethod
    def _flatten_disk(disk):
        shelf = disk.get("shelf") if isinstance(disk.get("shelf"), dict) else {}
        return {
            "name": _text(disk.get("name")),
            "serial_number": _text(disk.get("serial_number") or disk.get("uid")),
            "vendor": _text(disk.get("vendor")),
            "model": _text(disk.get("model")),
            "type": _text(disk.get("type")),
            "usable_size": disk.get("usable_size") if disk.get("usable_size") not in (None, "") else "",
            "rpm": disk.get("rpm") if disk.get("rpm") not in (None, "") else "",
            "state": _text(disk.get("state")),
            "bay": disk.get("bay") if disk.get("bay") not in (None, "") else "",
            "shelf": _text(shelf.get("uid") or shelf.get("name")),
        }

    def _flatten_volume(self, volume):
        aggregates = volume.get("aggregates") if isinstance(volume.get("aggregates"), list) else []
        parent = ""
        if aggregates and isinstance(aggregates[0], dict):
            parent = _text(aggregates[0].get("name"))
        space = volume.get("space") if isinstance(volume.get("space"), dict) else {}
        return {
            "name": _text(volume.get("name")),
            "uuid": _text(volume.get("uuid")),
            "type": _text(volume.get("type")),
            "state": _text(volume.get("state")),
            "parent_pool": parent,
            "wwn": self._volume_wwn(volume),
            "size": space.get("size") if space.get("size") not in (None, "") else "",
            "used": space.get("used") if space.get("used") not in (None, "") else "",
            "kind": "volume",
        }

    def _flatten_lun(self, lun):
        location = lun.get("location") if isinstance(lun.get("location"), dict) else {}
        volume = location.get("volume") if isinstance(location.get("volume"), dict) else {}
        space = lun.get("space") if isinstance(lun.get("space"), dict) else {}
        status = lun.get("status") if isinstance(lun.get("status"), dict) else {}
        return {
            "name": _text(lun.get("name")),
            "uuid": _text(lun.get("uuid")),
            "type": _text(lun.get("class") or lun.get("os_type")),
            "state": _text(status.get("state") or lun.get("state")),
            "parent_pool": "",
            "parent_volume": _text(volume.get("name")),
            "wwn": self._volume_wwn(lun),
            "serial_number": _text(lun.get("serial_number")),
            "size": space.get("size") if space.get("size") not in (None, "") else "",
            "used": space.get("used") if space.get("used") not in (None, "") else "",
            "kind": "lun",
        }

    def _ip_by_eth_port(self, interfaces):
        mapping = {}
        for item in interfaces:
            if not isinstance(item, dict):
                continue
            location = item.get("location") if isinstance(item.get("location"), dict) else {}
            port = location.get("port") if isinstance(location.get("port"), dict) else {}
            node = port.get("node") if isinstance(port.get("node"), dict) else {}
            ip = item.get("ip") if isinstance(item.get("ip"), dict) else {}
            address = _text(ip.get("address") or item.get("address") or item.get("ip"))
            name = _text(port.get("name"))
            if not name or not address:
                continue
            key = (name, _text(node.get("name")))
            mapping.setdefault(key, address)
            mapping.setdefault((name, ""), address)
        return mapping

    async def list_all_resources(self):
        self._client = httpx.AsyncClient(timeout=self.timeout, verify=self.verify_tls)
        try:
            cluster = await self._get_json("cluster", required=True)
            nodes = await self._fetch_records("cluster/nodes", fields="name,uuid,model,serial_number,version")
            pools = await self._fetch_records(
                "storage/aggregates",
                fields="name,uuid,state,space.block_storage",
            )
            disks = await self._fetch_records(
                "storage/disks",
                fields="name,uid,serial_number,vendor,model,type,usable_size,rpm,state,bay,shelf",
            )
            volumes = await self._fetch_records(
                "storage/volumes",
                fields="name,uuid,type,state,aggregates,space",
            )
            luns = await self._fetch_records(
                "storage/luns",
                fields="name,uuid,serial_number,os_type,class,space,location,status",
            )
            eth_ports = await self._fetch_records(
                "network/ethernet/ports",
                fields="name,uuid,mac_address,state,speed,node,type",
            )
            fc_ports = await self._fetch_records(
                "network/fc/ports",
                fields="name,uuid,wwpn,wwnn,state,speed,node",
            )
            interfaces = await self._fetch_records(
                "network/ip/interfaces",
                fields="name,ip,location,state,enabled",
            )

            ip_by_port = self._ip_by_eth_port(interfaces)
            flat_pools = [self._flatten_pool(item) for item in pools]
            flat_disks = [self._flatten_disk(item) for item in disks]
            flat_volumes = [self._flatten_volume(item) for item in volumes]
            flat_luns = [self._flatten_lun(item) for item in luns]
            flat_eth = [self._flatten_eth(item, ip_by_port) for item in eth_ports]
            flat_fc = [self._flatten_fc(item) for item in fc_ports]

            total = used = avail = 0
            for pool in flat_pools:
                total += _bytes_to_gb(pool.get("total_bytes"))
                used += _bytes_to_gb(pool.get("used_bytes"))
                avail += _bytes_to_gb(pool.get("available_bytes"))

            model = self._first_node_field(nodes, "model")
            device_sn = _text(cluster.get("uuid")) or self._first_node_field(nodes, "serial_number", "uuid")
            firmware = self._cluster_firmware(cluster) or self._first_node_field(nodes, "version")
            if not firmware and nodes:
                firmware = self._cluster_firmware(nodes[0])

            storage = {
                "device_sn": device_sn,
                "ip_addr": self.host,
                "model": model,
                "brand": "netapp",
                "storage_type": "unified",
                "firmware_version": firmware,
                "sys_desc": _text(cluster.get("name")) or "NetApp ONTAP",
                "total_capacity": str(total),
                "used_capacity": str(used),
                "available_capacity": str(avail),
                "pool_count": str(len(flat_pools)),
                "disk_count": str(len(flat_disks)),
                "volume_count": str(len(flat_volumes) + len(flat_luns)),
                "state": _text(cluster.get("state") or "online"),
            }
            return {
                "result": {
                    "storage": [storage],
                    "storage_pool": flat_pools,
                    "storage_disk": flat_disks,
                    "storage_volume": flat_volumes + flat_luns,
                    "storage_eth_port": flat_eth,
                    "storage_fc_port": flat_fc,
                },
                "success": True,
            }
        except Exception as err:  # noqa
            logger.exception(
                "event=netapp_ontap_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
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
