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

# push 路径必须持久化 node_id / monitor_id；与 pull sync 的 HOST_SYNC_UPDATE_FIELDS 刻意相反
HOST_INGEST_UPDATE_FIELDS = (
    "inst_name",
    "ip_addr",
    "organization",
    "cloud",
    "os_type",
    "node_id",
    "monitor_id",
)

# 网络设备 / physcial_server：无 cloud/os_type
IP_ONLY_INGEST_UPDATE_FIELDS = (
    "inst_name",
    "ip_addr",
    "organization",
    "node_id",
    "monitor_id",
)

# 系统内置联动 ID：落在模型属性上供图存储/查询，但对用户隐藏（非模型设计字段、非 CRUD）
SYSTEM_LINK_ATTR_IDS = frozenset({"node_id", "monitor_id"})

# 与 attr-host 中 str 字段（如 ip_addr）对齐的最小可创建形态；各模型复用
MODEL_NODE_ID_ATTR = {
    "attr_id": "node_id",
    "attr_name": "节点ID",
    "attr_type": "str",
    "attr_group": "系统联动",
    "editable": False,
    "is_only": True,
    "is_required": False,
    "is_system_link": True,
    "option": {
        "validation_type": "unrestricted",
        "custom_regex": "",
        "widget_type": "single_line",
    },
    "user_prompt": "系统内置联动字段，不对用户开放编辑",
    "default_value": [],
}

MODEL_MONITOR_ID_ATTR = {
    "attr_id": "monitor_id",
    "attr_name": "监控实例ID",
    "attr_type": "str",
    "attr_group": "系统联动",
    "editable": False,
    "is_only": True,
    "is_required": False,
    "is_system_link": True,
    "option": {
        "validation_type": "unrestricted",
        "custom_regex": "",
        "widget_type": "single_line",
    },
    "user_prompt": "系统内置联动字段，不对用户开放编辑",
    "default_value": [],
}

# 向后兼容别名
HOST_NODE_ID_ATTR = MODEL_NODE_ID_ATTR
HOST_MONITOR_ID_ATTR = MODEL_MONITOR_ID_ATTR

RECEIVING_MODULE = "cmdb"


def is_system_link_attr(attr: dict[str, Any] | None) -> bool:
    """系统内置联动属性：不对用户暴露于模型设计 / CRUD。"""
    if not isinstance(attr, dict):
        return False
    attr_id = str(attr.get("attr_id") or "").strip()
    if attr_id in SYSTEM_LINK_ATTR_IDS:
        return True
    return bool(attr.get("is_system_link"))


def filter_user_facing_attrs(attrs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """过滤掉系统联动属性，供模型设计与实例 CRUD 表单使用。"""
    return [attr for attr in (attrs or []) if not is_system_link_attr(attr)]


def strip_system_link_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    """从用户请求 payload 中剔除系统联动字段，防止手工写入。"""
    data = dict(payload or {})
    for key in SYSTEM_LINK_ATTR_IDS:
        data.pop(key, None)
    return data


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
    """确保指定模型具备系统内置 node_id 属性（可写给 ingest，对用户隐藏）。"""
    return _ensure_system_link_attr(
        model_id,
        attr_id="node_id",
        template=MODEL_NODE_ID_ATTR,
        username=username,
    )


def ensure_host_node_id_attr(*, username: str = "admin") -> bool:
    """确保 host 模型具备可写 node_id 属性（向后兼容包装）。"""
    return ensure_model_node_id_attr("host", username=username)


def ensure_model_monitor_id_attr(model_id: str, *, username: str = "admin") -> bool:
    """确保指定模型具备系统内置 monitor_id 属性（可写给 ingest，对用户隐藏）。"""
    return _ensure_system_link_attr(
        model_id,
        attr_id="monitor_id",
        template=MODEL_MONITOR_ID_ATTR,
        username=username,
    )


def ensure_host_monitor_id_attr(*, username: str = "admin") -> bool:
    """确保 host 模型具备可写 monitor_id 属性（向后兼容包装）。"""
    return ensure_model_monitor_id_attr("host", username=username)


def _ensure_system_link_attr(
    model_id: str,
    *,
    attr_id: str,
    template: dict[str, Any],
    username: str,
) -> bool:
    from apps.cmdb.services.model import ModelManage

    model_info = ModelManage.search_model_info(model_id)
    if not model_info:
        logger.warning(
            "[ModuleIngest] %s 模型不存在，无法 ensure %s attr", model_id, attr_id
        )
        return False

    attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
    existing = next((attr for attr in attrs if attr.get("attr_id") == attr_id), None)
    if existing is not None:
        # 存量属性升级为系统内置形态（editable=False / is_system_link）
        needs_upgrade = (
            existing.get("editable") is not False
            or not existing.get("is_system_link")
            or existing.get("attr_group") != template.get("attr_group")
        )
        if needs_upgrade:
            try:
                patched = dict(existing)
                patched.update(
                    {
                        "editable": False,
                        "is_system_link": True,
                        "attr_group": template.get("attr_group"),
                        "user_prompt": template.get("user_prompt") or patched.get("user_prompt") or "",
                    }
                )
                ModelManage.update_model_attr(model_id, patched, username=username)
            except Exception:
                logger.exception(
                    "[ModuleIngest] upgrade %s.%s to system link failed",
                    model_id,
                    attr_id,
                )
        return True

    try:
        ModelManage.create_model_attr(model_id, dict(template), username=username)
    except BaseAppException as exc:
        message = str(getattr(exc, "message", "") or exc)
        if "repetition" in message.lower() or "重复" in message:
            logger.info(
                "[ModuleIngest] %s.%s 属性已存在（并发创建），视为就绪",
                model_id,
                attr_id,
            )
            return True
        raise

    logger.info("[ModuleIngest] 已为 %s 模型创建系统联动属性 %s", model_id, attr_id)
    return True


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
        monitor_id = link_ids.get("monitor_id")
        node_id = str(node_id).strip() if node_id not in (None, "") else None
        cmdb_id = str(cmdb_id).strip() if cmdb_id not in (None, "") else None
        monitor_id = (
            str(monitor_id).strip() if monitor_id not in (None, "") else None
        )

        # 回声抑制：本模块自推，或 causation 标明由本模块出站引起的回写
        if cls._is_echo(params):
            return IngestResult(id=cmdb_id, ignored=True).as_dict()

        event_type = str(params.get("event_type") or EVENT_UPSERT).strip()
        if event_type == EVENT_LIFECYCLE:
            return cls._handle_lifecycle(
                raw=raw,
                source_module=source_module,
                node_id=node_id,
                cmdb_id=cmdb_id,
                monitor_id=monitor_id,
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

        # 仅在需要写入关联指针时 ensure attr
        if node_id and not ensure_model_node_id_attr(
            model_id, username=operator or "admin"
        ):
            raise ValueError(
                f"{model_id}.node_id attribute is required but could not be ensured"
            )
        if monitor_id and not ensure_model_monitor_id_attr(
            model_id, username=operator or "admin"
        ):
            raise ValueError(
                f"{model_id}.monitor_id attribute is required but could not be ensured"
            )

        desired = cls._build_desired(
            model_id=model_id,
            raw=raw,
            node_id=node_id,
            monitor_id=monitor_id,
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
        source_module: str,
        node_id: str | None,
        cmdb_id: str | None,
        monitor_id: str | None,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        """跨模块删除通知：CMDB 永不因对端删除而硬删实例，只清关联 ID。

        - node_mgmt 退役：清 node_id
        - monitor 删除通知：清 monitor_id
        - 其他：按携带的 link 字段清对应指针
        """
        action = str((raw or {}).get("action") or "retire").strip().lower()
        if action not in ("retire", "archive", "stop", "unlink", ""):
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
            model_id = "host"
            try:
                model_id = resolve_ingest_model_id(raw) if raw else "host"
            except ValueError:
                model_id = "host"
            existing = cls._find_by_node_id(model_id, node_id)
        if not existing and monitor_id:
            existing = cls._find_by_monitor_id(monitor_id)

        if not existing:
            logger.info(
                "[ModuleIngest] lifecycle no-op: instance not found cmdb_id=%s node_id=%s monitor_id=%s",
                cmdb_id,
                node_id,
                monitor_id,
            )
            return IngestResult(id=cmdb_id, ignored=True).as_dict()

        inst_id = existing.get("_id")
        clear_fields: dict[str, str] = {}
        if source_module == "node_mgmt":
            if str(existing.get("node_id") or "").strip():
                clear_fields["node_id"] = ""
        elif source_module == "monitor":
            if str(existing.get("monitor_id") or "").strip():
                clear_fields["monitor_id"] = ""
        else:
            # 兜底：按传入 link 清对应字段
            if node_id and str(existing.get("node_id") or "").strip():
                clear_fields["node_id"] = ""
            if monitor_id and str(existing.get("monitor_id") or "").strip():
                clear_fields["monitor_id"] = ""

        if not clear_fields:
            return IngestResult(id=inst_id, ignored=True).as_dict()

        model_id = str(existing.get("model_id") or "host")
        if "node_id" in clear_fields:
            ensure_model_node_id_attr(model_id, username=operator or "admin")
        if "monitor_id" in clear_fields:
            ensure_model_monitor_id_attr(model_id, username=operator or "admin")

        updated = InstanceManage.instance_update(
            user_groups=[],
            roles=[],
            inst_id=int(inst_id),
            update_attr=clear_fields,
            operator=operator,
            allowed_org_ids=list(allowed_org_ids or []),
            skip_permission_check=True,
        )
        logger.info(
            "[ModuleIngest] lifecycle unlink cleared %s on inst_id=%s source=%s",
            sorted(clear_fields.keys()),
            inst_id,
            source_module,
        )
        return IngestResult(
            id=(updated.get("_id") if isinstance(updated, dict) else inst_id),
            updated=True,
        ).as_dict()

    @classmethod
    def _find_by_monitor_id(cls, monitor_id: str) -> dict[str, Any] | None:
        """按 monitor_id 查找（主机一期）。"""
        if not monitor_id:
            return None
        try:
            found = InstanceManage.query_entity_by_identity(
                "host", {"monitor_id": monitor_id}
            )
        except Exception:
            logger.exception(
                "[ModuleIngest] 按 monitor_id 查找失败 monitor_id=%s", monitor_id
            )
            return None
        return found or None

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
        cls,
        *,
        model_id: str,
        raw: dict[str, Any],
        node_id: str | None,
        monitor_id: str | None = None,
    ) -> dict[str, Any]:
        if model_id == "host":
            return cls._build_host_desired(
                raw=raw, node_id=node_id, monitor_id=monitor_id
            )
        return cls._build_ip_only_desired(
            model_id=model_id, raw=raw, node_id=node_id, monitor_id=monitor_id
        )

    @classmethod
    def _build_host_desired(
        cls,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        monitor_id: str | None = None,
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
        if monitor_id:
            desired["monitor_id"] = monitor_id
        return desired

    @classmethod
    def _build_ip_only_desired(
        cls,
        *,
        model_id: str,
        raw: dict[str, Any],
        node_id: str | None,
        monitor_id: str | None = None,
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
        if monitor_id:
            desired["monitor_id"] = monitor_id
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
