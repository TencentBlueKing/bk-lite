from dataclasses import dataclass, field

from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectTriggerClient

SCAN_CREDENTIAL_RESULT_SUBJECT = "receive_scan_credential_result"


@dataclass
class ScanShot:
    id: int
    model_id: str
    driver_type: str
    ip_range: str
    instances: list
    credential: list
    timeout: int
    access_point: list
    params: dict = field(default_factory=lambda: {"has_network_topo": False})

    @property
    def decrypt_credentials(self):
        return self.credential


def join_ip_ranges(ip_ranges) -> str:
    parts = []
    for item in ip_ranges or []:
        if not isinstance(item, dict):
            continue
        begin = str(item.get("begin") or "").strip()
        end = str(item.get("end") or "").strip()
        if begin and end:
            parts.append(f"{begin}-{end}")
    return ",".join(parts)


def build_scan_collect_headers(shot: ScanShot) -> dict:
    node_params = NodeParamsFactory.get_node_params(shot)
    raw_headers = node_params.custom_headers()
    env_config = node_params.env_config() or {}
    resolve = StargazerCollectTriggerClient._resolve_env_placeholder
    headers = {key: resolve(value, env_config) for key, value in raw_headers.items() if key.startswith("cmdb")}
    tags = getattr(node_params, "tags", {}) or {}
    headers.update(
        {
            "instance_id": str(tags.get("instance_id") or ""),
            "instance_type": str(tags.get("instance_type") or ""),
            "collect_type": str(tags.get("collect_type") or "http"),
            "config_type": str(tags.get("config_type") or shot.model_id),
        }
    )
    headers["cmdbcredential_result_subject"] = SCAN_CREDENTIAL_RESULT_SUBJECT
    return headers
