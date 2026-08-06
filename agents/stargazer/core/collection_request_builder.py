"""把 HTTP 参数规范化为一个多目标 CollectionRequest。"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping, Sequence

from core.collection_runtime import CollectionRequest


_CREDENTIAL_KEYS = {
    "credential_id",
    "credential_version",
    "username",
    "user",
    "password",
    "token",
    "secret_id",
    "secret_key",
    "community",
    "private_key",
    "private_key_content",
    "private_key_passphrase",
    "passphrase",
    "auth_type",
    "version",
    "security_level",
    "auth_protocol",
    "auth_key",
    "priv_protocol",
    "priv_key",
}
_DEFAULT_PORTS = {
    "mysql": 3306,
    "gbase8a": 3306,
    "postgresql": 5432,
    "pgsql": 5432,
    "greenplum": 5432,
    "kingbase": 5432,
    "opengauss": 5432,
    "vastbase": 5432,
    "mssql": 1433,
    "oracle": 1521,
    "influxdb": 8086,
    "vmware": 443,
    "vmware_vc": 443,
    "windows_wmi": 135,
}
_CLOUD_TYPES = {"aliyun", "qcloud", "hwcloud"}
_FLATTENED_CREDENTIAL_KEY = re.compile(r"^credential_\d+_.+$")


def build_collection_request(
    *, task_id: str, params: Mapping[str, Any]
) -> CollectionRequest:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        raise ValueError("task_id is required")
    source = dict(params or {})
    monitor_type = str(source.get("monitor_type") or "").strip()
    model_id = str(source.get("model_id") or "").strip()
    family = "monitor" if monitor_type else "configuration"
    plugin_name = monitor_type or model_id or str(source.get("plugin_name") or "")
    if not plugin_name:
        raise ValueError("monitor_type or model_id is required")

    max_targets = int(os.getenv("MAX_TARGETS_PER_RUN", "10000"))
    raw_targets = source.get("targets", source.get("hosts"))
    if isinstance(raw_targets, Sequence) and not isinstance(
        raw_targets, (str, bytes, bytearray)
    ) and len(raw_targets) > max_targets:
        raise ValueError(
            f"target count {len(raw_targets)} exceeds MAX_TARGETS_PER_RUN={max_targets}"
        )
    if isinstance(raw_targets, str) and raw_targets.count(",") + 1 > max_targets:
        raise ValueError("target count exceeds MAX_TARGETS_PER_RUN")
    targets, logical_target = _targets(source, plugin_name)
    if len(targets) > max_targets:
        raise ValueError(
            f"target count {len(targets)} exceeds MAX_TARGETS_PER_RUN={max_targets}"
        )
    credentials = _credentials(source)
    max_credentials = int(os.getenv("MAX_CREDENTIALS_PER_RUN", "100"))
    if len(credentials) > max_credentials:
        raise ValueError(
            f"credential count {len(credentials)} exceeds MAX_CREDENTIALS_PER_RUN={max_credentials}"
        )
    public_params = {
        key: value
        for key, value in source.items()
        if key not in _CREDENTIAL_KEYS
        and key not in {"credentials_pool", "hosts", "targets"}
        and key != "credential_count"
        and not _FLATTENED_CREDENTIAL_KEY.fullmatch(str(key))
    }
    public_params["plugin_family"] = family
    public_params.setdefault("scope_id", str(source.get("scope_id") or "default"))
    public_params.setdefault(
        "credential_set_version",
        str(source.get("credential_set_version") or "default"),
    )
    public_params["target_is_logical"] = logical_target
    _apply_preflight_defaults(public_params, plugin_name, family)

    return CollectionRequest(
        task_id=normalized_task_id,
        plugin_ref=f"{plugin_name}.{'monitor' if monitor_type else 'config'}",
        targets=targets,
        credentials=credentials,
        params=public_params,
    )


def _targets(source: dict[str, Any], plugin_name: str) -> tuple[tuple[str, ...], bool]:
    raw_targets = source.get("targets", source.get("hosts"))
    if isinstance(raw_targets, str):
        raw_targets = [item.strip() for item in raw_targets.split(",")]
    if isinstance(raw_targets, Sequence) and not isinstance(
        raw_targets, (str, bytes, bytearray)
    ):
        targets = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in raw_targets
                if str(item).strip()
            )
        )
        if targets:
            return targets, False
    host = str(source.get("host") or source.get("base_url") or "").strip()
    if host:
        return (host,), False
    logical = str(
        (source.get("tags") or {}).get("instance_id")
        or source.get("instance_id")
        or plugin_name
    )
    return (logical,), True


def _credentials(source: dict[str, Any]) -> tuple[Mapping[str, Any], ...]:
    pool = source.get("credentials_pool")
    if isinstance(pool, str) and pool.strip():
        pool = json.loads(pool)
    if isinstance(pool, Sequence) and not isinstance(
        pool, (str, bytes, bytearray)
    ):
        credentials = [dict(item) for item in pool if isinstance(item, Mapping)]
    else:
        credentials = []
    if not credentials:
        credential = {
            key: source[key] for key in _CREDENTIAL_KEYS if key in source
        }
        credentials = [credential] if credential else [{}]
    for index, credential in enumerate(credentials, 1):
        credential.setdefault("credential_id", f"credential-{index}")
    return tuple(credentials)


def _apply_preflight_defaults(
    params: dict[str, Any], plugin_name: str, family: str
) -> None:
    if params.get("preflight_kind"):
        return
    if plugin_name in _CLOUD_TYPES:
        params["preflight_kind"] = "cloud"
        return
    if plugin_name in {"network", "network_topo"}:
        params["preflight_kind"] = "snmp"
        params.setdefault("port", 161)
        return
    if plugin_name == "host":
        params["preflight_kind"] = "remote"
        return
    if (
        family == "configuration"
        and str(params.get("executor_type") or "").lower() == "job"
        and not params.get("target_is_logical")
    ):
        params["preflight_kind"] = "remote"
        return
    if params.get("base_url"):
        params["preflight_kind"] = "https"
        return
    port = params.get("port") or _DEFAULT_PORTS.get(plugin_name)
    if port:
        params["port"] = int(port)
        params["preflight_kind"] = "tcp"
    else:
        params["preflight_kind"] = "none"
