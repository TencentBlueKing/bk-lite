"""跨模块推送写入监控：按 link_ids.node_id / cmdb_id 归并 upsert。

一期：最小实例 upsert + ID 归并，不开采集配置流水线。
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import (
    CollectConfig,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
)
from apps.monitor.utils.dimension import normalize_instance_identity
from apps.node_mgmt.services.module_push_contract import (
    EVENT_LIFECYCLE,
    EVENT_UPSERT,
    LINK_CONFLICT,
    IngestResult,
)
from apps.rpc.node_mgmt import NodeMgmt

HOST_OBJECT_NAME = "Host"
RECEIVING_MODULE = "monitor"

# CMDB → 监控：允许「有凭据则创建资产并自动监控」的对象范围（按 CMDB model_id）。
# 适配范围外的对象一律只做关联/回填，不创建。先做主机，其他对象逐步纳入。
CMDB_CREATE_ADAPTED_MODEL_IDS = frozenset({"host"})

# CMDB 带凭据创建资产+默认策略路径：一期先关闭（默认对象列表未齐），保留扩展开关。
CMDB_CREDENTIAL_CREATE_ENABLED = False

# 节点推送创建场景：默认套用 Telegraf 主机（agent）模板
HOST_AGENT_COLLECTOR = "Telegraf"
HOST_AGENT_COLLECT_TYPE = "host"
DEFAULT_HOST_COLLECT_MODULES = ("cpu", "disk", "diskio", "mem", "net", "processes", "system")
DEFAULT_COLLECT_INTERVAL = 60
DEFAULT_DISK_EXCLUDE_FSTYPES = (
    "tmpfs,devtmpfs,devfs,iso9660,overlay,aufs,squashfs,vfat,exfat,fat,fat32"
)

# CMDB 带凭据创建场景：套用 Host Remote（远程采集）模板
HOST_REMOTE_COLLECT_TYPE = "http"
HOST_REMOTE_CONFIG_TYPE = "host"


class MonitorModuleIngestService:
    """接收 node_mgmt / CMDB 等模块推送的 ingest envelope，写入 MonitorInstance。"""

    @classmethod
    def ingest(cls, params: dict[str, Any]) -> dict[str, Any]:
        allowed_org_ids = params.get("allowed_org_ids")
        if not allowed_org_ids:
            raise ValueError("authorization scope is required for monitor ingest")

        raw = params.get("raw") or {}
        if not isinstance(raw, dict):
            raise ValueError("raw must be an object")

        link_ids = params.get("link_ids") or {}
        if not isinstance(link_ids, dict):
            link_ids = {}

        node_id = cls._normalize_optional_str(link_ids.get("node_id"))
        cmdb_id = cls._normalize_optional_str(link_ids.get("cmdb_id"))
        monitor_id = cls._normalize_optional_str(link_ids.get("monitor_id"))
        # node_mgmt 信封常把节点 ID 放在 source_id；勿把 CMDB source_id 误当作 node_id
        if not node_id and params.get("source_module") == "node_mgmt":
            node_id = cls._normalize_optional_str(params.get("source_id"))

        # 回声抑制：本模块自推，或 causation 标明由本模块出站引起的回写
        if cls._is_echo(params):
            existing = None
            if monitor_id:
                existing = cls._find_by_pk(monitor_id)
            if not existing and node_id:
                existing = cls._find_by_node_id(node_id)
            if not existing and cmdb_id:
                existing = cls._find_by_cmdb_id(cmdb_id)
            return IngestResult(
                id=existing.id if existing else None,
                ignored=True,
            ).as_dict()

        event_type = str(params.get("event_type") or EVENT_UPSERT).strip()
        if event_type == EVENT_LIFECYCLE:
            return cls._handle_lifecycle(
                raw=raw,
                source_module=str(params.get("source_module") or ""),
                node_id=node_id,
                cmdb_id=cmdb_id,
                monitor_id=monitor_id,
                operator=str(params.get("operator") or ""),
            )

        operator = str(params.get("operator") or "")
        allowed = [int(x) for x in allowed_org_ids]

        by_node = cls._find_by_node_id(node_id) if node_id else None
        by_cmdb = cls._find_by_cmdb_id(cmdb_id) if cmdb_id else None

        if by_node and by_cmdb and by_node.id != by_cmdb.id:
            logger.warning(
                "[MonitorModuleIngest] link_conflict node_id=%s cmdb_id=%s "
                "by_node=%s by_cmdb=%s",
                node_id,
                cmdb_id,
                by_node.id,
                by_cmdb.id,
            )
            return IngestResult(
                id=by_node.id,
                conflict=LINK_CONFLICT,
                created=False,
                updated=False,
                claimed=False,
            ).as_dict()

        existing = by_node or by_cmdb
        if existing:
            updated = cls._update_instance(
                existing,
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                operator=operator,
                allowed_org_ids=allowed,
            )
            result = IngestResult(id=updated.id, updated=True).as_dict()
            # 节点推送超时重试会走更新分支：若尚无 Telegraf/host 采集配置则补套
            if (
                str(params.get("source_module") or "") == "node_mgmt"
                and node_id
                and not CollectConfig.objects.filter(
                    monitor_instance_id=updated.id,
                    collector=HOST_AGENT_COLLECTOR,
                    collect_type=HOST_AGENT_COLLECT_TYPE,
                ).exists()
            ):
                collect_error = cls._apply_agent_host_collect(
                    updated,
                    node_id=node_id,
                    raw=raw,
                    allowed_org_ids=allowed,
                )
                if collect_error:
                    result["collect_error"] = collect_error
            return result

        return cls._create_for_source(
            source_module=str(params.get("source_module") or ""),
            raw=raw,
            node_id=node_id,
            cmdb_id=cmdb_id,
            operator=operator,
            allowed_org_ids=allowed,
        )

    # ----- 创建场景分流：按来源模块决定是否建资产 / 套用采集模板 -----

    @classmethod
    def _create_for_source(
        cls,
        *,
        source_module: str,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        """未命中任何已有实例时的创建分流。

        统一原则（CMDB → 监控）：
          - 已有实例：只更新建链 / 回填 cmdb_id（本方法不处理）。
          - 创建资产并自动监控：必须同时满足「传了凭据」+「对象在适配范围内」。
          - 无凭据或未适配对象：不创建，仅关联；走到这里说明无可建关系 → ignored。

        当前适配范围：CMDB model_id ∈ CMDB_CREATE_ADAPTED_MODEL_IDS（先只含 host）。

        节点管理推送创建：创建实例并默认套用 Telegraf 主机模板（采集节点=该节点）。
        """
        if source_module == "cmdb":
            credential = cls._extract_credential(raw)
            model_id = cls._resolve_cmdb_model_id(raw)
            if (
                not CMDB_CREDENTIAL_CREATE_ENABLED
                or not credential
                or model_id not in CMDB_CREATE_ADAPTED_MODEL_IDS
            ):
                logger.info(
                    "[MonitorModuleIngest] cmdb push skip create "
                    "(enabled=%s credential=%s adapted=%s model_id=%s) "
                    "cmdb_id=%s node_id=%s",
                    CMDB_CREDENTIAL_CREATE_ENABLED,
                    bool(credential),
                    model_id in CMDB_CREATE_ADAPTED_MODEL_IDS,
                    model_id,
                    cmdb_id,
                    node_id,
                )
                return IngestResult(id=None, ignored=True).as_dict()

            instance, collect_error = cls._create_remote_host_instance(
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                credential=credential,
                operator=operator,
                allowed_org_ids=allowed_org_ids,
            )
            result = IngestResult(id=instance.id, created=True).as_dict()
            if collect_error:
                result["collect_error"] = collect_error
            return result

        if source_module == "node_mgmt" and node_id:
            created = cls._create_instance(
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                operator=operator,
                allowed_org_ids=allowed_org_ids,
            )
            collect_error = cls._apply_agent_host_collect(
                created,
                node_id=node_id,
                raw=raw,
                allowed_org_ids=allowed_org_ids,
            )
            result = IngestResult(id=created.id, created=True).as_dict()
            if collect_error:
                result["collect_error"] = collect_error
            return result

        created = cls._create_instance(
            raw=raw,
            node_id=node_id,
            cmdb_id=cmdb_id,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )
        return IngestResult(id=created.id, created=True).as_dict()

    @staticmethod
    def _resolve_cmdb_model_id(raw: dict[str, Any]) -> str:
        """从 envelope raw 解析 CMDB 模型；缺失时默认 host（与 CMDB ingest 对齐）。"""
        for key in ("model_id", "object_type", "device_type"):
            value = raw.get(key)
            if value not in (None, ""):
                return str(value).strip().lower()
        return "host"

    @staticmethod
    def _extract_credential(raw: dict[str, Any]) -> dict[str, Any] | None:
        """从 envelope raw 提取远程采集凭据；非 dict 或缺用户名视为未提供。"""
        credential = raw.get("credential")
        if not isinstance(credential, dict):
            return None
        username = str(credential.get("username") or "").strip()
        if not username:
            return None
        return credential

    @classmethod
    def _apply_agent_host_collect(
        cls,
        instance: MonitorInstance,
        *,
        node_id: str,
        raw: dict[str, Any],
        allowed_org_ids: list[int],
    ) -> str | None:
        """为节点推送创建的实例套用默认 Telegraf 主机模板（采集节点=该节点）。

        best-effort：失败不回滚实例创建，返回错误描述供 push_status 观察。
        """
        try:
            from apps.monitor.models import MonitorPlugin
            from apps.monitor.services.node_mgmt import InstanceConfigService

            plugin = (
                MonitorPlugin.objects.filter(
                    monitor_object=instance.monitor_object_id,
                    collector=HOST_AGENT_COLLECTOR,
                    collect_type=HOST_AGENT_COLLECT_TYPE,
                )
                .order_by("id")
                .first()
            )

            configs: list[dict[str, Any]] = []
            for module in DEFAULT_HOST_COLLECT_MODULES:
                config: dict[str, Any] = {
                    "type": module,
                    "interval": DEFAULT_COLLECT_INTERVAL,
                    "instance_type": "os",
                }
                if module == "disk":
                    config["disk_include_fstypes"] = ""
                    config["disk_exclude_fstypes"] = DEFAULT_DISK_EXCLUDE_FSTYPES
                configs.append(config)

            payload: dict[str, Any] = {
                "monitor_object_id": instance.monitor_object_id,
                "collector": HOST_AGENT_COLLECTOR,
                "collect_type": HOST_AGENT_COLLECT_TYPE,
                "configs": configs,
                "instances": [
                    {
                        "instance_id": node_id,
                        "instance_name": instance.name,
                        "node_ids": [node_id],
                        "group_ids": cls._normalize_org_ids(raw, allowed_org_ids),
                        "instance_type": "os",
                    }
                ],
            }
            if plugin:
                payload["monitor_plugin_id"] = plugin.id

            InstanceConfigService.create_monitor_instance_by_node_mgmt(payload)
            return None
        except Exception as exc:
            logger.warning(
                "[MonitorModuleIngest] apply agent host collect failed "
                "instance_id=%s node_id=%s: %s",
                instance.id,
                node_id,
                exc,
            )
            return str(exc)

    @classmethod
    def _create_remote_host_instance(
        cls,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        credential: dict[str, Any],
        operator: str,
        allowed_org_ids: list[int],
    ) -> tuple[MonitorInstance, str | None]:
        """CMDB 带凭据创建：走 Host Remote 远程采集模板。

        失败时回退为最小身份实例（不带采集配置），错误描述随结果返回。
        """
        ip = cls._extract_ip(raw)
        collector_node_id: str | None = None
        cloud: int | None = None
        error: str | None = None

        if not ip:
            error = "remote collect requires raw.ip"
        else:
            collector_node_id, cloud = cls._pick_container_node(raw, allowed_org_ids)
            if not collector_node_id:
                error = "no container collector node available for remote collect"
            elif cloud is None:
                # 默认云区域，避免实例 ID 出现 None 段
                cloud = 1

        if not error:
            try:
                from apps.monitor.services.node_mgmt import InstanceConfigService

                monitor_object = cls._resolve_monitor_object(raw)
                raw_instance_id = f"{cloud}_os_{ip}"
                InstanceConfigService.create_monitor_instance_by_node_mgmt(
                    {
                        "monitor_object_id": monitor_object.id,
                        "collector": HOST_AGENT_COLLECTOR,
                        "collect_type": HOST_REMOTE_COLLECT_TYPE,
                        "configs": [cls._build_remote_host_config(ip=ip, raw=raw, credential=credential)],
                        "instances": [
                            {
                                "instance_id": raw_instance_id,
                                "instance_name": cls._extract_name(raw, ip=ip),
                                "node_ids": [collector_node_id],
                                "group_ids": cls._normalize_org_ids(raw, allowed_org_ids),
                                "instance_type": "os",
                            }
                        ],
                    }
                )
                storage_key = normalize_instance_identity(raw_instance_id)[
                    "storage_instance_key"
                ]
                instance = cls._find_by_pk(storage_key)
                if instance is None:
                    error = "remote onboarding did not create instance"
                else:
                    update_fields: list[str] = []
                    linked = node_id
                    if not linked:
                        linked = cls._best_effort_auto_link_node(
                            monitor_id=instance.id, ip=ip, cloud=cloud
                        )
                    if linked and instance.node_id != linked:
                        instance.node_id = linked
                        update_fields.append("node_id")
                    if cmdb_id and instance.cmdb_id != cmdb_id:
                        instance.cmdb_id = cmdb_id
                        update_fields.append("cmdb_id")
                    if ip and instance.ip != ip:
                        instance.ip = ip
                        update_fields.append("ip")
                    if update_fields:
                        instance.save(update_fields=update_fields + ["updated_at"])
                    return instance, None
            except Exception as exc:
                logger.warning(
                    "[MonitorModuleIngest] remote host onboarding failed "
                    "cmdb_id=%s ip=%s: %s",
                    cmdb_id,
                    ip,
                    exc,
                )
                error = str(exc)

        instance = cls._create_instance(
            raw=raw,
            node_id=node_id,
            cmdb_id=cmdb_id,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )
        return instance, error

    @classmethod
    def _build_remote_host_config(
        cls,
        *,
        ip: str,
        raw: dict[str, Any],
        credential: dict[str, Any],
    ) -> dict[str, Any]:
        """把 CMDB 凭据映射为 Host Remote 模板字段；密钥经 ENV_* 走 env_config。"""
        os_type_raw = str(raw.get("os_type") or raw.get("operating_system") or "").lower()
        os_type = "windows" if "win" in os_type_raw else "linux"

        auth_type = str(credential.get("auth_type") or "").strip()
        if not auth_type:
            auth_type = "private_key" if credential.get("private_key") else "password"

        config: dict[str, Any] = {
            "type": HOST_REMOTE_CONFIG_TYPE,
            "interval": DEFAULT_COLLECT_INTERVAL,
            "host": ip,
            "os_type": os_type,
            "username": str(credential.get("username") or ""),
            "auth_type": auth_type,
            "port": credential.get("port") or "",
            "disk_include_fstypes": "",
            "disk_exclude_fstypes": DEFAULT_DISK_EXCLUDE_FSTYPES,
            "ENV_PASSWORD": str(credential.get("password") or ""),
        }
        private_key = credential.get("private_key") or credential.get("private_key_content")
        if private_key:
            config["ENV_PRIVATE_KEY_CONTENT"] = str(private_key)
        passphrase = credential.get("passphrase") or credential.get("private_key_passphrase")
        if passphrase:
            config["ENV_PRIVATE_KEY_PASSPHRASE"] = str(passphrase)
        return config

    @classmethod
    def _pick_container_node(
        cls,
        raw: dict[str, Any],
        allowed_org_ids: list[int],
    ) -> tuple[str | None, int | None]:
        """为远程采集自动选取容器采集节点；优先同云区域，其次全局。"""
        cloud = cls._extract_cloud_region_id(raw)
        org_ids = [int(x) for x in allowed_org_ids]

        def _query(cloud_region_id: int | None) -> dict[str, Any] | None:
            query: dict[str, Any] = {
                "is_container": True,
                "is_active": True,
                "organization_ids": org_ids,
                "page": 1,
                "page_size": 1,
            }
            if cloud_region_id is not None:
                query["cloud_region_id"] = cloud_region_id
            try:
                data = NodeMgmt().node_list(query) or {}
            except Exception as exc:
                logger.warning(
                    "[MonitorModuleIngest] container node lookup failed: %s", exc
                )
                return None
            nodes = data.get("nodes") or []
            return nodes[0] if nodes else None

        node = _query(cloud)
        if not node and cloud is not None:
            node = _query(None)
        if not node:
            return None, cloud
        node_cloud = node.get("cloud_region_id") or cloud
        try:
            node_cloud = int(node_cloud) if node_cloud is not None else None
        except (TypeError, ValueError):
            node_cloud = cloud
        return str(node.get("id")), (cloud if cloud is not None else node_cloud)

    @staticmethod
    def _normalize_optional_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _is_echo(cls, params: dict[str, Any]) -> bool:
        source_module = str(params.get("source_module") or "")
        if source_module == RECEIVING_MODULE:
            return True
        causation_id = str(params.get("causation_id") or "")
        return causation_id.startswith(f"{RECEIVING_MODULE}:")

    @classmethod
    def _handle_lifecycle(
        cls,
        *,
        raw: dict[str, Any],
        source_module: str,
        node_id: str | None,
        cmdb_id: str | None,
        monitor_id: str | None,
        operator: str,
    ) -> dict[str, Any]:
        """跨模块删除通知。

        - node_mgmt 退役：软删监控资产（停采/归档，不物理硬删）
        - cmdb / 其他：只清关联 ID，不删资产
        """
        action = str((raw or {}).get("action") or "retire").strip().lower()
        if action not in ("retire", "archive", "stop", "unlink", ""):
            logger.info(
                "[MonitorModuleIngest] lifecycle ignored unknown action=%s monitor_id=%s",
                action,
                monitor_id,
            )
            return IngestResult(id=monitor_id, ignored=True).as_dict()

        existing = None
        if monitor_id:
            existing = cls._find_by_pk(monitor_id)
        if not existing and node_id:
            existing = cls._find_by_node_id(node_id)
        if not existing and cmdb_id:
            existing = cls._find_by_cmdb_id(cmdb_id)

        if not existing:
            logger.info(
                "[MonitorModuleIngest] lifecycle no-op: instance not found "
                "monitor_id=%s node_id=%s cmdb_id=%s",
                monitor_id,
                node_id,
                cmdb_id,
            )
            return IngestResult(id=monitor_id, ignored=True).as_dict()

        # 节点删除确认清理：软删监控资产
        if source_module == "node_mgmt" and action in ("retire", "archive", "stop", ""):
            if existing.is_deleted and not existing.is_active:
                return IngestResult(id=existing.id, ignored=True).as_dict()

            update_fields = ["is_active", "is_deleted", "updated_at"]
            existing.is_active = False
            existing.is_deleted = True
            if operator:
                existing.updated_by = operator
                update_fields.append("updated_by")
            existing.save(update_fields=update_fields)
            logger.info(
                "[MonitorModuleIngest] lifecycle retire soft-deactivated instance_id=%s",
                existing.id,
            )
            return IngestResult(id=existing.id, updated=True).as_dict()

        # 其他模块删除：只清关联 ID
        clear_fields: list[str] = []
        if source_module == "cmdb":
            if existing.cmdb_id:
                existing.cmdb_id = None
                clear_fields.append("cmdb_id")
        else:
            if cmdb_id and existing.cmdb_id:
                existing.cmdb_id = None
                clear_fields.append("cmdb_id")
            if node_id and existing.node_id:
                existing.node_id = None
                clear_fields.append("node_id")

        if not clear_fields:
            return IngestResult(id=existing.id, ignored=True).as_dict()

        if operator:
            existing.updated_by = operator
            clear_fields.append("updated_by")
        clear_fields.append("updated_at")
        existing.save(update_fields=clear_fields)
        logger.info(
            "[MonitorModuleIngest] lifecycle unlink cleared %s on instance_id=%s source=%s",
            [f for f in clear_fields if f not in ("updated_at", "updated_by")],
            existing.id,
            source_module,
        )
        return IngestResult(id=existing.id, updated=True).as_dict()

    @classmethod
    def _find_by_pk(cls, instance_id: str) -> MonitorInstance | None:
        return (
            MonitorInstance.objects.filter(id=instance_id)
            .select_related("monitor_object")
            .first()
        )

    @classmethod
    def _find_by_node_id(cls, node_id: str) -> MonitorInstance | None:
        return (
            MonitorInstance.objects.filter(node_id=node_id, is_deleted=False)
            .select_related("monitor_object")
            .first()
        )

    @classmethod
    def _find_by_cmdb_id(cls, cmdb_id: str) -> MonitorInstance | None:
        return (
            MonitorInstance.objects.filter(cmdb_id=cmdb_id, is_deleted=False)
            .select_related("monitor_object")
            .first()
        )

    @classmethod
    def _resolve_monitor_object(cls, raw: dict[str, Any]) -> MonitorObject:
        object_id = raw.get("monitor_object_id")
        if object_id not in (None, ""):
            obj = MonitorObject.objects.filter(id=object_id).first()
            if obj:
                return obj
            raise ValueError(f"monitor_object_id not found: {object_id!r}")

        obj = MonitorObject.objects.filter(name=HOST_OBJECT_NAME).first()
        if obj:
            return obj
        raise ValueError(
            f"monitor object {HOST_OBJECT_NAME!r} not found; "
            "provide raw.monitor_object_id or create Host monitor object"
        )

    @classmethod
    def _extract_ip(cls, raw: dict[str, Any]) -> str | None:
        for key in ("ip", "ip_addr"):
            value = raw.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return None

    @classmethod
    def _extract_cloud_region_id(cls, raw: dict[str, Any]) -> int | None:
        value = raw.get("cloud_region_id") if "cloud_region_id" in raw else raw.get("cloud")
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_name(cls, raw: dict[str, Any], *, ip: str | None) -> str:
        name = str(raw.get("name") or raw.get("inst_name") or "").strip()
        if name:
            return name
        if ip:
            cloud_label = raw.get("cloud_region_name") or raw.get("cloud_region_id") or ""
            return f"{ip}[{cloud_label}]" if cloud_label != "" else ip
        return "unnamed"

    @classmethod
    def _normalize_org_ids(cls, raw: dict[str, Any], allowed_org_ids: list[int]) -> list[int]:
        raw_orgs = raw.get("organization_ids") if "organization_ids" in raw else raw.get("organization")
        if raw_orgs in (None, ""):
            return list(allowed_org_ids)
        if not isinstance(raw_orgs, (list, tuple, set)):
            raw_orgs = [raw_orgs]
        parsed: list[int] = []
        for item in raw_orgs:
            try:
                parsed.append(int(item))
            except (TypeError, ValueError):
                continue
        allowed_set = set(allowed_org_ids)
        in_scope = [org_id for org_id in parsed if org_id in allowed_set]
        return in_scope or list(allowed_org_ids)

    @classmethod
    def _new_instance_id(cls, *, node_id: str | None, raw: dict[str, Any]) -> str:
        if node_id:
            try:
                return normalize_instance_identity(node_id)["storage_instance_key"]
            except ValueError:
                pass
        cloud = cls._extract_cloud_region_id(raw)
        ip = cls._extract_ip(raw)
        if cloud is not None and ip:
            try:
                from apps.monitor.utils.dimension import build_safe_instance_id, extract_monitor_instance_id

                logical = build_safe_instance_id(cloud, ip)
                return extract_monitor_instance_id((logical,))
            except ValueError:
                pass
        return uuid.uuid4().hex

    @classmethod
    def _bind_organizations(
        cls,
        instance: MonitorInstance,
        org_ids: list[int],
        *,
        operator: str,
    ) -> None:
        existing = set(
            MonitorInstanceOrganization.objects.filter(monitor_instance=instance).values_list(
                "organization", flat=True
            )
        )
        for org_id in org_ids:
            if org_id in existing:
                continue
            MonitorInstanceOrganization.objects.create(
                monitor_instance=instance,
                organization=org_id,
                created_by=operator,
                updated_by=operator,
            )

    @classmethod
    @transaction.atomic
    def _update_instance(
        cls,
        instance: MonitorInstance,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        operator: str,
        allowed_org_ids: list[int],
    ) -> MonitorInstance:
        update_fields: list[str] = []
        ip = cls._extract_ip(raw)
        if ip and instance.ip != ip:
            instance.ip = ip
            update_fields.append("ip")

        cloud = cls._extract_cloud_region_id(raw)
        if cloud is not None and instance.cloud_region_id != cloud:
            instance.cloud_region_id = cloud
            update_fields.append("cloud_region_id")

        name = cls._extract_name(raw, ip=ip or (str(instance.ip) if instance.ip else None))
        if name and instance.name != name:
            instance.name = name
            update_fields.append("name")

        if node_id and instance.node_id != node_id:
            instance.node_id = node_id
            update_fields.append("node_id")

        if cmdb_id and instance.cmdb_id != cmdb_id:
            instance.cmdb_id = cmdb_id
            update_fields.append("cmdb_id")

        if instance.is_deleted:
            instance.is_deleted = False
            update_fields.append("is_deleted")

        if operator:
            instance.updated_by = operator
            update_fields.append("updated_by")

        if update_fields:
            instance.save(update_fields=update_fields + ["updated_at"])

        org_ids = cls._normalize_org_ids(raw, allowed_org_ids)
        cls._bind_organizations(instance, org_ids, operator=operator)
        return instance

    @classmethod
    @transaction.atomic
    def _create_instance(
        cls,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        operator: str,
        allowed_org_ids: list[int],
    ) -> MonitorInstance:
        monitor_object = cls._resolve_monitor_object(raw)
        ip = cls._extract_ip(raw)
        cloud = cls._extract_cloud_region_id(raw)
        name = cls._extract_name(raw, ip=ip)
        instance_id = cls._new_instance_id(node_id=node_id, raw=raw)

        # 主键冲突时回退 uuid，避免与存量云区域+IP 实例撞车阻断推送
        if MonitorInstance.objects.filter(id=instance_id).exists():
            instance_id = uuid.uuid4().hex

        instance = MonitorInstance.objects.create(
            id=instance_id,
            name=name,
            monitor_object=monitor_object,
            ip=ip,
            cloud_region_id=cloud,
            node_id=node_id,
            cmdb_id=cmdb_id,
            created_by=operator,
            updated_by=operator,
            is_deleted=False,
            is_active=True,
        )
        org_ids = cls._normalize_org_ids(raw, allowed_org_ids)
        cls._bind_organizations(instance, org_ids, operator=operator)

        # IoC：创建后通知节点 + CMDB（best-effort，异常不得影响本域创建）
        if monitor_object.name == HOST_OBJECT_NAME:
            try:
                cls._best_effort_notify_peers_on_create(
                    instance,
                    operator=operator,
                    allowed_org_ids=allowed_org_ids,
                )
                try:
                    instance.refresh_from_db()
                except Exception:
                    logger.exception(
                        "[MonitorModuleIngest] refresh after IoC hook failed instance_id=%s",
                        instance.id,
                    )
            except Exception:
                logger.exception(
                    "[MonitorModuleIngest] post-create IoC hook failed instance_id=%s",
                    instance.id,
                )

        logger.info(
            "[MonitorModuleIngest] created instance_id=%s node_id=%s cmdb_id=%s",
            instance.id,
            instance.node_id,
            cmdb_id,
        )
        return instance

    @classmethod
    def _best_effort_notify_peers_on_create(
        cls,
        instance: MonitorInstance,
        *,
        operator: str,
        allowed_org_ids: list[int],
    ) -> None:
        """监控主机新建钩子：通知节点（只关联）+ CMDB（create/update）。"""
        try:
            from apps.monitor.services.module_push import MonitorToCmdbPushService

            MonitorToCmdbPushService.best_effort_notify_on_host_create(
                instance,
                operator=operator,
                allowed_org_ids=allowed_org_ids,
            )
        except Exception:
            logger.exception(
                "[MonitorModuleIngest] IoC notify peers failed monitor_id=%s",
                instance.id,
            )

    @classmethod
    def _best_effort_auto_link_node(
        cls,
        *,
        monitor_id: str,
        ip: str | None,
        cloud: int | None,
    ) -> str | None:
        """兼容旧路径：直接本地关联。"""
        from apps.node_mgmt.services.module_link import NodeAssociationService

        return NodeAssociationService.best_effort_associate_monitor_host(
            monitor_id=monitor_id,
            ip=ip,
            cloud=cloud,
        )
