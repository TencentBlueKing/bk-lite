# -*- coding: utf-8 -*-
"""火山引擎配置采集。只拉清单，不调用监控代码。"""
from __future__ import annotations

import asyncio

from core.logger import logger, safe_exception_info, safe_log_value
from plugins.base_utils import encode_collected_tag
from plugins.inputs.volcengine.client import VolcengineApiError, VolcengineClient

_ECS_BIND = "EcsInstance"
_CLB_BIND = "ClbInstance"
_RESOURCE_ID_FIELD = {
    "volcengine_ecs": "InstanceId",
    "volcengine_eip": "AllocationId",
    "volcengine_clb": "LoadBalancerId",
    "volcengine_mysql": "InstanceId",
    "volcengine_pgsql": "InstanceId",
    "volcengine_tos": "Name",
}
_PRODUCTS = (
    ("volcengine_ecs", "describe_instances"),
    ("volcengine_clb", "describe_load_balancers"),
    ("volcengine_eip", "describe_eips"),
    ("volcengine_mysql", "describe_mysql"),
    ("volcengine_pgsql", "describe_postgresql"),
    ("volcengine_tos", "list_buckets"),
)


def _resource_id(model_id: str, row) -> str:
    if not isinstance(row, dict):
        return ""
    return _text(row.get(_RESOURCE_ID_FIELD.get(model_id, "")))


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _name(resource_name: str, resource_id: str) -> str:
    return resource_name or resource_id


def _time(value) -> str:
    text = _text(value).replace("T", " ").replace("Z", "")
    if "+" in text:
        text = text.split("+", 1)[0]
    if "." in text:
        text = text.split(".", 1)[0]
    return text[:19]


def _tags(raw) -> list[str]:
    tags = raw.get("Tags") or raw.get("TagSet") or []
    if isinstance(tags, dict):
        tags = tags.get("Tag") or tags.get("Tags") or []
    values = []
    for item in tags:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        key = _text(item.get("Key") or item.get("key"))
        if not key:
            continue
        encoded = encode_collected_tag(key, _text(item.get("Value") or item.get("value")))
        if encoded:
            values.append(encoded)
    return values[:50]


def _number(value) -> str:
    text = _text(value)
    return text if text else "0"


def _primary_ip(instance: dict) -> str:
    interfaces = instance.get("NetworkInterfaces") or []
    if isinstance(interfaces, dict):
        interfaces = [interfaces]
    primary = ""
    for nic in interfaces:
        if not isinstance(nic, dict):
            continue
        address = _text(nic.get("PrimaryIpAddress"))
        if _text(nic.get("Type")).lower() == "primary" and address:
            return address
        if address and not primary:
            primary = address
    return primary


def _public_ip(value) -> str:
    if isinstance(value, dict):
        return _text(value.get("IpAddress") or value.get("IPAddress") or value.get("EipAddress"))
    return _text(value)


def _private_address(instance: dict) -> tuple[str, str]:
    addresses = instance.get("AddressObject") or instance.get("Addresses") or []
    if isinstance(addresses, dict):
        addresses = [addresses]
    chosen = None
    for item in addresses:
        if not isinstance(item, dict):
            continue
        kind = _text(item.get("EipType") or item.get("Type") or item.get("NetworkType")).lower()
        if "private" in kind or kind in {"intranet", "inner"}:
            chosen = item
            break
        if chosen is None:
            chosen = item
    if not chosen:
        return "", ""
    ip = _text(chosen.get("IPAddress") or chosen.get("IpAddress") or chosen.get("Domain") or chosen.get("Address"))
    return ip, _number(chosen.get("Port")) if _text(chosen.get("Port")) else ""


class CwVolcengine:
    def __init__(self, params: dict, client: VolcengineClient | None = None):
        self.params = params or {}
        self.access_key = self.params.get("accessKey") or self.params.get("secret_id") or ""
        self.secret_key = self.params.get("accessSecret") or self.params.get("secret_key") or ""
        self.region = self.params.get("region") or self.params.get("region_id") or ""
        self.endpoint = self.params.get("host") or self.params.get("endpoint") or ""
        self._client = client

    def _inventory(self) -> VolcengineClient:
        if self._client is not None:
            return self._client
        return VolcengineClient(self.access_key, self.secret_key, self.region, self.endpoint)

    def list_regions(self):
        regions = self._inventory().describe_regions()
        result = []
        for item in regions:
            region_id = _text(item.get("RegionId") or item.get("region_id") or item.get("resource_id"))
            if not region_id:
                continue
            result.append({"resource_id": region_id, "resource_name": region_id})
        return result

    async def probe(self):
        from core.collection.contracts import AccessProbeResult, AccessProbeStatus

        try:
            await asyncio.to_thread(self.list_regions)
        except VolcengineApiError as exc:
            logger.warning(
                "event=volcengine_probe_denied region=%s failed_stage=probe error_type=%s error_code=%s",
                safe_log_value(self.region),
                type(exc).__name__,
                safe_log_value(exc.code),
            )
            return AccessProbeResult(status=_probe_status(exc), error_code=exc.code)
        except Exception as exc:  # noqa: BLE001 - 连通性失败不能带出响应正文
            logger.error(
                "event=volcengine_probe_failed region=%s failed_stage=probe error_type=%s",
                safe_log_value(self.region),
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            return AccessProbeResult(status=AccessProbeStatus.SERVICE_UNAVAILABLE, error_code="volcengine_probe_failed")
        return AccessProbeResult(status=AccessProbeStatus.READY)

    async def list_all_resources(self):
        return await asyncio.to_thread(self._list_all_resources_sync)

    def _list_all_resources_sync(self):
        client = self._inventory()
        result = {}
        for model_id, method_name in _PRODUCTS:
            try:
                rows = getattr(client, method_name)()
            except Exception as exc:  # noqa: BLE001 - 一类失败不能丢掉其余产品
                result[model_id] = [self._record_failure(model_id, exc, "")]
                continue
            collected = []
            for row in rows:
                resource_id = _resource_id(model_id, row)
                try:
                    if not self._keep(model_id, row):
                        continue
                    item = self._format(model_id, row)
                except Exception as exc:  # noqa: BLE001 - 单条失败保留同类其他资源
                    collected.append(self._record_failure(model_id, exc, resource_id))
                    continue
                if not item.get("resource_id"):
                    try:
                        raise VolcengineApiError("InvalidResource", "")
                    except VolcengineApiError as exc:
                        collected.append(self._record_failure(model_id, exc, ""))
                    continue
                collected.append(item)
            result[model_id] = collected
        return {"result": result, "success": True}

    def _record_failure(self, model_id: str, exc: BaseException, resource_id: str) -> dict:
        logger.error(
            "event=volcengine_product_failed region=%s product=%s resource_id=%s failed_stage=list error_type=%s error_code=%s",
            safe_log_value(self.region),
            model_id,
            safe_log_value(resource_id or "-"),
            type(exc).__name__,
            safe_log_value(getattr(exc, "code", "") or type(exc).__name__),
            exc_info=safe_exception_info(exc),
        )
        failed = {
            "collect_status": "failed",
            "cmdb_collect_error": str(getattr(exc, "code", "") or type(exc).__name__),
            "region": self.region,
            "product": model_id,
        }
        if resource_id:
            failed["resource_id"] = resource_id
        return failed

    def _keep(self, model_id: str, row: dict) -> bool:
        if model_id != "volcengine_tos":
            return True
        return _text(row.get("Location")) == self.region

    def _format(self, model_id: str, row: dict) -> dict:
        if model_id == "volcengine_ecs":
            return self._ecs(row)
        if model_id == "volcengine_eip":
            return self._eip(row)
        if model_id == "volcengine_clb":
            return self._clb(row)
        if model_id in {"volcengine_mysql", "volcengine_pgsql"}:
            return self._database(row)
        return self._bucket(row)

    def _base(self, resource_id: str, resource_name: str, row: dict) -> dict:
        return {
            "resource_id": resource_id,
            "resource_name": _name(resource_name, resource_id),
            "region": self.region,
            "tag": _tags(row),
        }

    def _ecs(self, row: dict) -> dict:
        resource_id = _text(row.get("InstanceId"))
        data = self._base(resource_id, _text(row.get("InstanceName")), row)
        data.update(
            {
                "ip_addr": _primary_ip(row),
                "public_ip": _public_ip(row.get("EipAddress")),
                "zone": _text(row.get("ZoneId")),
                "vpc": _text(row.get("VpcId")),
                "status": _text(row.get("Status")),
                "instance_type": _text(row.get("InstanceTypeId")),
                "os_name": _text(row.get("OsName")),
                "vcpus": _number(row.get("Cpus")),
                "memory_mb": _number(row.get("MemorySize")),
                "charge_type": _text(row.get("InstanceChargeType")),
                "create_time": _time(row.get("CreatedAt")),
                "expired_time": _time(row.get("ExpiredAt")),
            }
        )
        return data

    def _eip(self, row: dict) -> dict:
        resource_id = _text(row.get("AllocationId"))
        data = self._base(resource_id, _text(row.get("Name") or row.get("EipAddress")), row)
        data.update(
            {
                "ip_addr": _text(row.get("EipAddress")),
                "status": _text(row.get("Status")),
                "bandwidth": _number(row.get("Bandwidth")),
                "bind_instance_type": _text(row.get("InstanceType")),
                "bind_instance_id": _text(row.get("InstanceId")),
            }
        )
        return data

    def _clb(self, row: dict) -> dict:
        resource_id = _text(row.get("LoadBalancerId"))
        data = self._base(resource_id, _text(row.get("LoadBalancerName")), row)
        data.update(
            {
                "vpc": _text(row.get("VpcId")),
                "ip_addr": _text(row.get("Address") or row.get("EniAddress")),
                "public_ip": _public_ip(row.get("EipAddress")),
                "status": _text(row.get("Status")),
                "type": _text(row.get("Type")),
                "charge_type": _text(row.get("LoadBalancerBillingType")),
                "create_time": _time(row.get("CreateTime")),
            }
        )
        return data

    def _database(self, row: dict) -> dict:
        resource_id = _text(row.get("InstanceId"))
        ip_addr, port = _private_address(row)
        data = self._base(resource_id, _text(row.get("InstanceName")), row)
        data.update(
            {
                "zone": _text(row.get("ZoneId")),
                "vpc": _text(row.get("VpcId")),
                "ip_addr": ip_addr,
                "port": port,
                "version": _text(row.get("DBEngineVersion")),
                "status": _text(row.get("InstanceStatus")),
                "storage_gb": _number(row.get("StorageSpace")),
                "storage_type": _text(row.get("StorageType")),
                "charge_type": _text(row.get("ChargeType") or row.get("InstanceChargeType")),
                "create_time": _time(row.get("CreateTime")),
            }
        )
        return data

    def _bucket(self, row: dict) -> dict:
        resource_id = _text(row.get("Name"))
        data = self._base(resource_id, resource_id, row)
        data.update(
            {
                "location": _text(row.get("Location")),
                "extranet_endpoint": _text(row.get("ExtranetEndpoint")),
                "intranet_endpoint": _text(row.get("IntranetEndpoint")),
                "bucket_type": _text(row.get("BucketType")),
                "creation_date": _time(row.get("CreationDate")),
            }
        )
        return data


def _probe_status(exc: VolcengineApiError):
    from core.collection.enums import AccessProbeStatus

    code = exc.code.lower()
    if exc.code in {"FlowLimitExceeded", "RequestLimitExceeded", "Throttling"}:
        return AccessProbeStatus.RATE_LIMITED
    if "denied" in code or "forbidden" in code:
        return AccessProbeStatus.CAPABILITY_DENIED
    if any(token in code for token in ("auth", "signature", "invalidaccess", "invalidsecret")):
        return AccessProbeStatus.AUTH_FAILED
    return AccessProbeStatus.SERVICE_UNAVAILABLE
