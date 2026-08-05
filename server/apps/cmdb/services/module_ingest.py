"""跨模块推送写入 CMDB：按模型 ID 优先 upsert + 存量认领。

路由字段（按优先级）：
  raw.model_id → raw.object_type → raw.device_type → 默认 host

一期支持模型：
  host（ip+cloud 认领）
  switch / router / firewall / loadbalance / physcial_server（仅 ip_addr 认领）
"""

from __future__ import annotations

from typing import Any

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.node_mgmt.services.module_push_contract import (
    EVENT_LIFECYCLE,
    EVENT_UPSERT,
    LINK_CONFLICT,
    IngestResult,
)

# 一期 ingest 支持的模型（physcial_server 拼写与存量模型 id 对齐）
SUPPORTED_INGEST_MODELS = frozenset(
    {
        "host",
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "physcial_server",
    }
)

# 无 cloud 字段、仅按 ip_addr 认领的模型
IP_ONLY_CLAIM_MODELS = frozenset(
    {
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "physcial_server",
    }
)

# push 路径必须持久化 node_id；与 pull sync 的 HOST_SYNC_UPDATE_FIELDS 刻意相反
HOST_INGEST_UPDATE_FIELDS = (
    "inst_name",
    "ip_addr",
    "organization",
    "cloud",
    "os_type",
    "node_id",
)

# 网络设备 / physcial_server：无 cloud/os_type
IP_ONLY_INGEST_UPDATE_FIELDS = (
    "inst_name",
    "ip_addr",
    "organization",
    "node_id",
)

# 与 attr-host 中 str 字段（如 ip_addr）对齐的最小可创建形态；各模型复用
MODEL_NODE_ID_ATTR = {
    "attr_id": "node_id",
    "attr_name": "节点ID",
    "attr_type": "str",
    "attr_group": "基本信息",
    "editable": True,
    "is_only": True,
    "is_required": False,
    "option": {
        "validation_type": "unrestricted",
        "custom_regex": "",
        "widget_type": "single_line",
    },
    "user_prompt": "",
    "default_value": [],
}

# 向后兼容别名
HOST_NODE_ID_ATTR = MODEL_NODE_ID_ATTR

RECEIVING_MODULE = "cmdb"


def resolve_ingest_model_id(raw: dict[str, Any]) -> str:
    """从 envelope raw 解析目标模型。

    优先级：model_id → object_type → device_type；缺失则默认 host。
    """
    for key in ("model_id", "object_type", "device_type"):
        value = raw.get(key)
        if value is None or value == "":
            continue
        model_id = str(value).strip()
        if model_id not in SUPPORTED_INGEST_MODELS:
            raise ValueError(
                f"unsupported model_id for CMDB ingest: {model_id!r}; "
                f"supported={sorted(SUPPORTED_INGEST_MODELS)}"
            )
        return model_id
    return "host"


def ensure_model_node_id_attr(model_id: str, *, username: str = "admin") -> bool:
    """确保指定模型具备可写 node_id 属性。

    Returns:
        True 表示属性已就绪（已存在 / 本次新建 / 并发重复创建成功）；
        False 表示仍不可用（如模型缺失）。
    """
    from apps.cmdb.services.model import ModelManage

    model_info = ModelManage.search_model_info(model_id)
    if not model_info:
        logger.warning(
            "[ModuleIngest] %s 模型不存在，无法 ensure node_id attr", model_id
        )
        return False

    attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
    if any(attr.get("attr_id") == "node_id" for attr in attrs):
        return True

    try:
        ModelManage.create_model_attr(
            model_id, dict(MODEL_NODE_ID_ATTR), username=username
        )
    except BaseAppException as exc:
        # 并发场景下另一进程已创建：视为幂等就绪
        message = str(getattr(exc, "message", "") or exc)
        if "repetition" in message.lower() or "重复" in message:
            logger.info(
                "[ModuleIngest] %s.node_id 属性已存在（并发创建），视为就绪",
                model_id,
            )
            return True
        raise

    logger.info("[ModuleIngest] 已为 %s 模型创建可写 node_id 属性", model_id)
    return True


def ensure_host_node_id_attr(*, username: str = "admin") -> bool:
    """确保 host 模型具备可写 node_id 属性（向后兼容包装）。"""
    return ensure_model_node_id_attr("host", username=username)


class CmdbModuleIngestService:
    """接收 node_mgmt 等模块推送的 ingest envelope，写入 CMDB 对应模型。"""

    @classmethod
    def ingest(cls, params: dict[str, Any]) -> dict[str, Any]:
        allowed_org_ids = params.get("allowed_org_ids")
        if not allowed_org_ids:
            raise ValueError("authorization scope is required for CMDB ingest")

        raw = params.get("raw") or {}
        if not isinstance(raw, dict):
            raise ValueError("raw must be an object")

        link_ids = params.get("link_ids") or {}
        if not isinstance(link_ids, dict):
            link_ids = {}

        source_module = str(params.get("source_module") or "")
        node_id = link_ids.get("node_id")
        if not node_id and source_module == "node_mgmt":
            node_id = params.get("source_id")
        cmdb_id = link_ids.get("cmdb_id")
        node_id = str(node_id).strip() if node_id not in (None, "") else None
        cmdb_id = str(cmdb_id).strip() if cmdb_id not in (None, "") else None

        # 回声抑制：本模块自推，或 causation 标明由本模块出站引起的回写
        if cls._is_echo(params):
            return IngestResult(id=cmdb_id, ignored=True).as_dict()

        event_type = str(params.get("event_type") or EVENT_UPSERT).strip()
        if event_type == EVENT_LIFECYCLE:
            return cls._handle_lifecycle(
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                operator=params.get("operator") or "",
                allowed_org_ids=list(allowed_org_ids),
            )

        if not node_id and not cmdb_id and not cls._extract_ip(raw):
            raise ValueError(
                "link_ids.node_id, link_ids.cmdb_id, or raw ip is required"
            )

        operator = params.get("operator") or ""
        model_id = resolve_ingest_model_id(raw)
        update_fields = cls._update_fields_for(model_id)

        # 仅在需要写入 node_id 时 ensure attr
        if node_id and not ensure_model_node_id_attr(
            model_id, username=operator or "admin"
        ):
            raise ValueError(
                f"{model_id}.node_id attribute is required but could not be ensured"
            )

        desired = cls._build_desired(
            model_id=model_id, raw=raw, node_id=node_id
        )

        # 1) 有 node_id → 只按 node_id upsert（未命中则走认领/新建，不回落到 cmdb_id）
        if node_id:
            existing = cls._find_by_node_id(model_id, node_id)
            if existing:
                updated = cls._update_instance(
                    existing,
                    desired,
                    update_fields=update_fields,
                    operator=operator,
                    allowed_org_ids=list(allowed_org_ids),
                )
                return IngestResult(id=updated.get("_id"), updated=True).as_dict()
        # 2) 无 node_id 但有 cmdb_id → 按实例 ID 更新
        elif cmdb_id:
            existing = cls._find_by_cmdb_id(cmdb_id)
            if existing:
                updated = cls._update_instance(
                    existing,
                    desired,
                    update_fields=update_fields,
                    operator=operator,
                    allowed_org_ids=list(allowed_org_ids),
                )
                return IngestResult(id=updated.get("_id"), updated=True).as_dict()

        # 3) 未按 ID 命中：存量认领
        existing = cls._find_for_claim(model_id, desired)
        if existing:
            existing_node_id = str(existing.get("node_id") or "").strip()
            incoming_node_id = str(desired.get("node_id") or "").strip()
            # 存量已绑定其他 node_id：禁止劫持覆盖
            if (
                incoming_node_id
                and existing_node_id
                and existing_node_id != incoming_node_id
            ):
                logger.warning(
                    "[ModuleIngest] claim link_conflict model=%s existing_id=%s "
                    "existing_node_id=%s incoming_node_id=%s",
                    model_id,
                    existing.get("_id"),
                    existing_node_id,
                    incoming_node_id,
                )
                return IngestResult(
                    id=existing.get("_id"),
                    conflict=LINK_CONFLICT,
                    claimed=False,
                    updated=False,
                    created=False,
                ).as_dict()
            claimed = cls._claim_instance(
                existing,
                desired,
                update_fields=update_fields,
                operator=operator,
                allowed_org_ids=list(allowed_org_ids),
            )
            return IngestResult(id=claimed.get("_id"), claimed=True).as_dict()

        created = cls._create_instance(
            model_id,
            desired,
            update_fields=update_fields,
            operator=operator,
            allowed_org_ids=list(allowed_org_ids),
        )
        return IngestResult(id=created.get("_id"), created=True).as_dict()

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
        node_id: str | None,
        cmdb_id: str | None,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        """处理 lifecycle 退役：不解绑外不硬删。

        Concern：CMDB Neo4j 实例无统一 soft-delete/archive 字段；一期仅清除
        node_id 关联指针，实例本体保留。若未来有归档语义，应在此扩展。
        """
        action = str((raw or {}).get("action") or "retire").strip().lower()
        if action not in ("retire", "archive", "stop", ""):
            logger.info(
                "[ModuleIngest] lifecycle ignored unknown action=%s cmdb_id=%s node_id=%s",
                action,
                cmdb_id,
                node_id,
            )
            return IngestResult(id=cmdb_id, ignored=True).as_dict()

        existing = None
        if cmdb_id:
            existing = cls._find_by_cmdb_id(cmdb_id)
        if not existing and node_id:
            # 无 model_id 时默认按 host 查找；与一期节点推送落模一致
            model_id = "host"
            try:
                model_id = resolve_ingest_model_id(raw) if raw else "host"
            except ValueError:
                model_id = "host"
            existing = cls._find_by_node_id(model_id, node_id)

        if not existing:
            logger.info(
                "[ModuleIngest] lifecycle no-op: instance not found cmdb_id=%s node_id=%s",
                cmdb_id,
                node_id,
            )
            return IngestResult(id=cmdb_id, ignored=True).as_dict()

        inst_id = existing.get("_id")
        existing_node_id = str(existing.get("node_id") or "").strip()
        if not existing_node_id:
            logger.info(
                "[ModuleIngest] lifecycle already unlinked inst_id=%s (CMDB 无 archive 语义，仅解绑)",
                inst_id,
            )
            return IngestResult(id=inst_id, ignored=True).as_dict()

        # 仅清除 node_id；禁止 hard delete
        updated = InstanceManage.instance_update(
            user_groups=[{"id": org_id} for org_id in allowed_org_ids],
            roles=[],
            inst_id=int(inst_id),
            update_attr={"node_id": ""},
            operator=operator,
            allowed_org_ids=allowed_org_ids,
            skip_permission_check=False,
        )
        logger.warning(
            "[ModuleIngest] lifecycle retire: cleared node_id on inst_id=%s; "
            "CMDB 无 soft-archive，未物理删除实例",
            inst_id,
        )
        return IngestResult(
            id=(updated.get("_id") if isinstance(updated, dict) else inst_id),
            updated=True,
        ).as_dict()

    @classmethod
    def _find_by_cmdb_id(cls, cmdb_id: str) -> dict[str, Any] | None:
        try:
            found = InstanceManage.query_entity_by_id(int(cmdb_id))
        except (TypeError, ValueError):
            return None
        except Exception:
            logger.exception("[ModuleIngest] 按 cmdb_id 查找失败 cmdb_id=%s", cmdb_id)
            raise
        return found or None

    @classmethod
    def _update_fields_for(cls, model_id: str) -> tuple[str, ...]:
        if model_id == "host":
            return HOST_INGEST_UPDATE_FIELDS
        return IP_ONLY_INGEST_UPDATE_FIELDS

    @classmethod
    def _extract_ip(cls, raw: dict[str, Any]) -> str:
        """从 raw 提取管理/业务 IP；BMC 场景兼容 bmc_ip。"""
        for key in ("ip", "ip_addr", "bmc_ip"):
            value = raw.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @classmethod
    def _build_desired(
        cls, *, model_id: str, raw: dict[str, Any], node_id: str | None
    ) -> dict[str, Any]:
        if model_id == "host":
            return cls._build_host_desired(raw=raw, node_id=node_id)
        return cls._build_ip_only_desired(model_id=model_id, raw=raw, node_id=node_id)

    @classmethod
    def _build_host_desired(
        cls, *, raw: dict[str, Any], node_id: str | None
    ) -> dict[str, Any]:
        ip = cls._extract_ip(raw)
        cloud_raw = raw.get("cloud_region_id") if "cloud_region_id" in raw else raw.get("cloud")
        try:
            cloud = int(cloud_raw) if cloud_raw not in (None, "") else None
        except (TypeError, ValueError):
            cloud = None

        organization = NodeMgmtSyncService._normalize_org_ids(
            raw.get("organization_ids") if "organization_ids" in raw else raw.get("organization")
        )
        inst_name = str(raw.get("name") or raw.get("inst_name") or "").strip()
        if not inst_name and ip:
            cloud_label = raw.get("cloud_region_name") or (cloud if cloud is not None else "")
            inst_name = f"{ip}[{cloud_label}]"

        os_type = NodeMgmtSyncService._map_host_os_type(
            raw.get("operating_system") or raw.get("os_type")
        )

        desired = {
            "model_id": "host",
            "inst_name": inst_name,
            "ip_addr": ip,
            "organization": organization,
            "cloud": cloud,
            "os_type": os_type,
        }
        if node_id:
            desired["node_id"] = node_id
        return desired

    @classmethod
    def _build_ip_only_desired(
        cls, *, model_id: str, raw: dict[str, Any], node_id: str | None
    ) -> dict[str, Any]:
        ip = cls._extract_ip(raw)
        organization = NodeMgmtSyncService._normalize_org_ids(
            raw.get("organization_ids") if "organization_ids" in raw else raw.get("organization")
        )
        inst_name = str(raw.get("name") or raw.get("inst_name") or "").strip()
        if not inst_name and ip:
            inst_name = ip

        desired = {
            "model_id": model_id,
            "inst_name": inst_name,
            "ip_addr": ip,
            "organization": organization,
        }
        if node_id:
            desired["node_id"] = node_id
        return desired

    @classmethod
    def _find_by_node_id(cls, model_id: str, node_id: str) -> dict[str, Any] | None:
        if not node_id:
            return None
        try:
            found = InstanceManage.query_entity_by_identity(
                model_id, {"node_id": node_id}
            )
        except Exception:
            logger.exception(
                "[ModuleIngest] 按 node_id 查找失败 model=%s node_id=%s",
                model_id,
                node_id,
            )
            raise
        return found or None

    @classmethod
    def _find_for_claim(
        cls, model_id: str, desired: dict[str, Any]
    ) -> dict[str, Any] | None:
        if model_id == "host":
            return cls._find_host_by_ip_cloud(
                desired.get("ip_addr"), desired.get("cloud")
            )
        if model_id in IP_ONLY_CLAIM_MODELS:
            return cls._find_by_ip_addr(model_id, desired.get("ip_addr"))
        raise ValueError(f"unsupported claim model: {model_id!r}")

    @classmethod
    def _find_host_by_ip_cloud(cls, ip_addr: Any, cloud: Any) -> dict[str, Any] | None:
        ip, normalized_cloud = NodeMgmtSyncService._host_lookup_key(
            {"ip_addr": ip_addr, "cloud": cloud}
        )
        if not ip or normalized_cloud is None:
            return None
        try:
            found = InstanceManage.query_entity_by_identity(
                "host",
                {"ip_addr": ip, "cloud": normalized_cloud},
            )
        except Exception:
            logger.exception(
                "[ModuleIngest] 按 ip+cloud 查找 host 失败 ip=%s cloud=%s",
                ip,
                normalized_cloud,
            )
            raise
        return found or None

    @classmethod
    def _find_by_ip_addr(cls, model_id: str, ip_addr: Any) -> dict[str, Any] | None:
        ip = str(ip_addr or "").strip()
        if not ip:
            return None
        try:
            found = InstanceManage.query_entity_by_identity(
                model_id, {"ip_addr": ip}
            )
        except Exception:
            logger.exception(
                "[ModuleIngest] 按 ip_addr 查找失败 model=%s ip=%s",
                model_id,
                ip,
            )
            raise
        return found or None

    @classmethod
    def _update_payload(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
        update_fields: tuple[str, ...],
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field in update_fields:
            if field not in desired:
                continue
            value = desired.get(field)
            if value in (None, "", []):
                continue
            if existing.get(field) != value:
                changes[field] = value
        return changes

    @classmethod
    def _update_instance(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
        *,
        update_fields: tuple[str, ...],
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        changes = cls._update_payload(existing, desired, update_fields)
        if not changes:
            return existing
        updated = InstanceManage.instance_update(
            user_groups=[{"id": org_id} for org_id in allowed_org_ids],
            roles=[],
            inst_id=int(existing["_id"]),
            update_attr=changes,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
            skip_permission_check=False,
        )
        return updated if isinstance(updated, dict) else {**existing, **changes}

    @classmethod
    def _claim_instance(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
        *,
        update_fields: tuple[str, ...],
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        # 认领：白名单字段；有 incoming node_id 时强制写入（调用方须已排除异 node_id 冲突）
        existing_node_id = str(existing.get("node_id") or "").strip()
        incoming_node_id = str(desired.get("node_id") or "").strip()
        if existing_node_id and incoming_node_id and existing_node_id != incoming_node_id:
            raise ValueError(
                f"cannot claim instance already linked to node_id={existing_node_id}"
            )
        changes = cls._update_payload(existing, desired, update_fields)
        if incoming_node_id:
            changes["node_id"] = desired["node_id"]
        if not changes:
            return existing
        updated = InstanceManage.instance_update(
            user_groups=[{"id": org_id} for org_id in allowed_org_ids],
            roles=[],
            inst_id=int(existing["_id"]),
            update_attr=changes,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
            skip_permission_check=False,
        )
        return updated if isinstance(updated, dict) else {**existing, **changes}

    @classmethod
    def _create_instance(
        cls,
        model_id: str,
        desired: dict[str, Any],
        *,
        update_fields: tuple[str, ...],
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        payload = {
            field: desired[field]
            for field in update_fields
            if field in desired and desired.get(field) not in (None, "")
        }
        created = InstanceManage.instance_create(
            model_id=model_id,
            instance_info=payload,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )
        return created if isinstance(created, dict) else payload

    # ----- host 向后兼容包装（既有单测直接调用） -----

    @classmethod
    def _host_update_payload(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
    ) -> dict[str, Any]:
        return cls._update_payload(existing, desired, HOST_INGEST_UPDATE_FIELDS)

    @classmethod
    def _update_host(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
        *,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        return cls._update_instance(
            existing,
            desired,
            update_fields=HOST_INGEST_UPDATE_FIELDS,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )

    @classmethod
    def _claim_host(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
        *,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        return cls._claim_instance(
            existing,
            desired,
            update_fields=HOST_INGEST_UPDATE_FIELDS,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )

    @classmethod
    def _create_host(
        cls,
        desired: dict[str, Any],
        *,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        return cls._create_instance(
            "host",
            desired,
            update_fields=HOST_INGEST_UPDATE_FIELDS,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )
