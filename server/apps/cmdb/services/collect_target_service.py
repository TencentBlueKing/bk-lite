from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from typing import Any

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.core.logger import cmdb_logger as logger


@dataclass(frozen=True)
class CanonicalCollectTarget:
    """任务内可连接目标的标准表示，用于命中判断与 object_key 生成。"""

    task_id: int
    task_type: str
    executor: str
    model_id: str
    host: str
    port: int | None = None
    endpoint: str | None = None
    cloud_region_id: str | None = None
    instance_id: str | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)


class CollectTargetService:
    """负责把任务快照转为任务内标准目标集合。"""

    @staticmethod
    def build_targets(task) -> list[CanonicalCollectTarget]:
        """从 task.instances / task.ip_range 构建标准目标列表。"""
        targets = []
        if task.instances:
            for instance in task.instances:
                target = CollectTargetService._build_instance_target(task, instance)
                targets.append(target)
        else:
            for host in CollectTargetService._expand_ip_range(task.ip_range):
                targets.append(
                    CanonicalCollectTarget(
                        task_id=task.id,
                        task_type=task.task_type,
                        executor="job" if task.is_job else "protocol",
                        model_id=task.model_id,
                        host=host,
                        port=CollectTargetService._resolve_target_port(task, {}),
                        snapshot={"host": host, "ip": host, "model_id": task.model_id},
                    )
                )

        for target in targets:
            logger.info(
                "[CollectTarget] build object key task_id=%s object_key=%s model_id=%s",
                task.id,
                CollectTargetService.build_object_key(target),
                target.model_id,
            )
        return targets

    @staticmethod
    def build_object_key(target: CanonicalCollectTarget) -> str:
        """按任务类型生成稳定 object_key。"""
        if target.task_type in {CollectPluginTypes.HOST, CollectPluginTypes.MIDDLEWARE}:
            return f"{target.task_id}:{target.host}:{target.cloud_region_id or '-'}"
        if target.task_type in {CollectPluginTypes.DB, CollectPluginTypes.CONFIG_FILE}:
            endpoint = target.endpoint or target.port or "-"
            return f"{target.task_id}:{target.host}:{target.cloud_region_id or '-'}:{endpoint}"
        if target.task_type == CollectPluginTypes.SNMP:
            return f"{target.task_id}:{target.host}:{target.port or '-'}:{target.cloud_region_id or '-'}"
        endpoint = target.endpoint or target.port or "-"
        return f"{target.task_id}:{target.host}:{endpoint}"

    @staticmethod
    def build_target_snapshot(target: CanonicalCollectTarget) -> dict[str, Any]:
        """返回用于命中状态持久化与日志的最小快照。"""
        return {
            "host": target.host,
            "port": target.port,
            "endpoint": target.endpoint,
            "cloud_region_id": target.cloud_region_id,
            "instance_id": target.instance_id,
            "model_id": target.model_id,
            **(target.snapshot or {}),
        }

    @staticmethod
    def _build_instance_target(task, instance: dict[str, Any]) -> CanonicalCollectTarget:
        host = str(
            instance.get("ip")
            or instance.get("ip_addr")
            or instance.get("inst_name")
            or instance.get("name")
            or ""
        )
        port = CollectTargetService._resolve_target_port(task, instance)
        endpoint = instance.get("endpoint")
        cloud_region_id = str(instance.get("cloud_id") or instance.get("cloud_region_id") or "") or None
        instance_id = str(instance.get("_id") or instance.get("id") or "") or None
        return CanonicalCollectTarget(
            task_id=task.id,
            task_type=task.task_type,
            executor="job" if task.is_job else "protocol",
            model_id=instance.get("model_id") or task.model_id,
            host=host,
            port=port,
            endpoint=endpoint,
            cloud_region_id=cloud_region_id,
            instance_id=instance_id,
            snapshot=dict(instance or {}),
        )

    @staticmethod
    def _resolve_target_port(task, instance: dict[str, Any]) -> int | None:
        credential = task.decrypt_credentials
        if isinstance(credential, list):
            credential = credential[0] if credential else {}
        credential = credential or {}
        for value in (
            instance.get("port"),
            instance.get("snmp_port"),
            (task.params or {}).get("port"),
            credential.get("snmp_port"),
            credential.get("port"),
        ):
            try:
                if value in (None, ""):
                    continue
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _expand_ip_range(raw_ip_range: str | None) -> list[str]:
        """支持逗号/换行分隔和 start-end 形式的 IP 范围展开。"""
        if not raw_ip_range:
            return []

        hosts = []
        for line in str(raw_ip_range).splitlines():
            for part in line.split(","):
                token = part.strip()
                if not token:
                    continue
                if "-" in token:
                    start_text, end_text = [segment.strip() for segment in token.split("-", 1)]
                    try:
                        start_ip = ipaddress.ip_address(start_text)
                        end_ip = ipaddress.ip_address(end_text)
                    except ValueError:
                        hosts.append(token)
                        continue
                    start_num = int(start_ip)
                    end_num = int(end_ip)
                    if end_num < start_num:
                        start_num, end_num = end_num, start_num
                    hosts.extend(str(ipaddress.ip_address(index)) for index in range(start_num, end_num + 1))
                    continue
                hosts.append(token)
        return hosts