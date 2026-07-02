# -- coding: utf-8 --
import ipaddress
import json

from apps.cmdb.constants.constants import INSTANCE, CollectDriverTypes
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.node_configs.base import BaseNodeParams


DEFAULT_SCAN_PORTS = [22, 80, 443, 3389]


class IPDiscoveryNodeParams(BaseNodeParams):
    supported_model_id = "ip"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "ip_discovery"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "protocol"

    def get_hosts(self):
        return "hosts", ""

    def set_credential(self, *args, **kwargs):
        params = self._task_params()
        ports = params.get("ports") or DEFAULT_SCAN_PORTS
        if not isinstance(ports, list):
            ports = [ports]

        return {
            "scan_method": (params.get("scan_method") or "icmp").lower(),
            "ports": json.dumps(ports),
            "subnets": json.dumps(self._load_subnet_scopes(), ensure_ascii=False),
        }

    def env_config(self, *args, **kwargs):
        return {}

    def _task_params(self) -> dict:
        params = getattr(self.instance, "params", None) or {}
        instances = getattr(self.instance, "instances", None) or {}
        merged = {}
        if isinstance(instances, dict):
            merged.update(instances)
        if isinstance(params, dict):
            merged.update(params)
        return merged

    def _subnet_ids(self) -> list[int]:
        raw_ids = self._task_params().get("subnet_ids") or []
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]
        return [int(item) for item in raw_ids if str(item).strip()]

    def _load_subnet_scopes(self) -> list[dict]:
        subnet_ids = self._subnet_ids()
        if not subnet_ids:
            return []

        with GraphClient() as ag:
            rows, _ = ag.query_entity(
                INSTANCE,
                [
                    {"field": "model_id", "type": "str=", "value": "subnet"},
                    {"field": "id", "type": "id[]", "value": subnet_ids},
                ],
            )

        reserved_from_task = {
            str(item).strip()
            for item in (self._task_params().get("reserved_addresses") or [])
            if str(item).strip()
        }
        scopes = []
        for row in rows or []:
            cidr = self._to_cidr(row.get("subnet_address"), row.get("subnet_mask"))
            if not cidr:
                continue
            gateway = str(row.get("gateway") or "").strip()
            reserved = set(reserved_from_task)
            if gateway:
                reserved.add(gateway)
            scopes.append(
                {
                    "subnet_id": row.get("_id") or row.get("id"),
                    "cidr": cidr,
                    "gateway": gateway,
                    "reserved_addresses": sorted(reserved),
                }
            )
        return scopes

    @staticmethod
    def _to_cidr(address, mask) -> str:
        try:
            return str(ipaddress.ip_network(f"{str(address).strip()}/{str(mask).strip()}", strict=False))
        except (ValueError, TypeError):
            return ""
