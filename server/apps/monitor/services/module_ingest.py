"""跨模块推送写入监控：按 node_id → cmdb_id → 对象类型身份 → 同名 归并 upsert。

节点来源创建/补采集必须命中 Host + Telegraf 主机模板；找不到或套用失败则整次失败。
"""

from __future__ import annotations

import base64
import re
import uuid
from typing import Any

from django.db import transaction

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig, MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.utils.dimension import normalize_instance_identity
from apps.node_mgmt.services.module_push_contract import EVENT_LIFECYCLE, EVENT_UPSERT, LINK_CONFLICT, IngestResult
from apps.rpc.node_mgmt import NodeMgmt

HOST_OBJECT_NAME = "Host"
HOST_PLUGIN_NAME = "Host"
RECEIVING_MODULE = "monitor"
# 接入页偶发把默认名「IP-switch」编进网络设备主键；认领时只取前面的 IPv4。
_IPV4_WITH_OPTIONAL_SUFFIX = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})(?:-.+)?$")

# CMDB → 监控：允许「有凭据则创建资产并自动监控」的对象范围（按 CMDB model_id）。
# 适配范围外的对象一律只做关联/回填，不创建。全局开关默认关；扫描显式推送走 allow_credential_create。
CMDB_CREATE_ADAPTED_MODEL_IDS = frozenset(
    {
        "host",
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "physcial_server",
        "mysql",
        "postgresql",
        "mssql",
        "influxdb",
    }
)

# CMDB 带凭据创建资产+默认策略路径：默认关闭，避免节点创建钩子突然建监控。
CMDB_CREDENTIAL_CREATE_ENABLED = False

CMDB_MODEL_TO_MONITOR_OBJECT = {
    "host": HOST_OBJECT_NAME,
    "switch": "Switch",
    "router": "Router",
    "firewall": "Firewall",
    "loadbalance": "Loadbalance",
    "physcial_server": "Hardware Server",
    "mysql": "Mysql",
    "postgresql": "Postgres",
    "mssql": "MSSQL",
    "influxdb": "InfluxDB",
}

# 扫描 / 带凭据创建按插件名查询，禁止写死数字 ID。名称与 builtin metrics.json 对齐。
CMDB_MODEL_TO_MONITOR_PLUGIN = {
    "host": "Host Remote",
    "switch": "Switch SNMP General",
    "router": "Router SNMP General",
    "firewall": "Firewall SNMP General",
    "loadbalance": "Loadbalance SNMP General",
    "physcial_server": "Hardware Server IPMI",
    "mysql": "Mysql",
    "postgresql": "Postgres",
    "mssql": "MSSQL",
    "influxdb": "InfluxDB",
}

DB_DEFAULT_PORTS = {
    "mysql": 3306,
    "postgres": 5432,
    "mssql": 1433,
    "influxdb": 8086,
}

HOST_REMOTE_METRICS_MODULES = ("cpu", "mem", "disk", "diskio", "net", "processes", "system")

# 节点推送创建场景：默认套用 Telegraf 主机（agent）模板
HOST_AGENT_COLLECTOR = "Telegraf"
HOST_AGENT_COLLECT_TYPE = "host"
DEFAULT_HOST_COLLECT_MODULES = ("cpu", "disk", "diskio", "mem", "net", "processes", "system")
DEFAULT_COLLECT_INTERVAL = 60
# 与 Switch SNMP General UI.json timeout.default_value 对齐；缺了会留下 {{ timeout }}s，Telegraf 整份配置解析失败。
DEFAULT_SNMP_TIMEOUT = 10
DEFAULT_DISK_EXCLUDE_FSTYPES = "tmpfs,devtmpfs,devfs,iso9660,overlay,aufs,squashfs,vfat,exfat,fat,fat32,cdfs"

# CMDB 带凭据创建场景：套用 Host Remote（远程采集）模板
HOST_REMOTE_PLUGIN_NAME = "Host Remote"
HOST_REMOTE_COLLECT_TYPE = "http"
HOST_REMOTE_CONFIG_TYPE = "host"


class MonitorModuleIngestService:
    """接收 node_mgmt / CMDB 等模块推送的 ingest envelope，写入 MonitorInstance。"""

    IP_CLOUD_CLAIM_MODELS = frozenset({"host", "switch", "router", "firewall", "loadbalance", "physcial_server", "influxdb"})
    IP_PORT_CLAIM_MODELS = frozenset({"mysql", "postgresql", "mssql"})

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
        cmdb_aliases = link_ids.get("cmdb_id_aliases") or []
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
                existing = cls._find_by_cmdb_id(cmdb_id, aliases=cmdb_aliases)
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
                cmdb_aliases=cmdb_aliases,
            )

        operator = str(params.get("operator") or "")
        allowed = [int(x) for x in allowed_org_ids]
        actor_context = params.get("actor_context")

        by_node = cls._find_by_node_id(node_id) if node_id else None
        by_cmdb = cls._find_by_cmdb_id(cmdb_id, aliases=cmdb_aliases) if cmdb_id else None

        if by_node and by_cmdb and by_node.id != by_cmdb.id:
            logger.warning(
                "[MonitorModuleIngest] link_conflict node_id=%s cmdb_id=%s " "by_node=%s by_cmdb=%s",
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
        if not existing:
            by_identity = cls._find_by_type_identity(raw)
            if by_identity:
                bound_node_id = cls._normalize_optional_str(by_identity.node_id)
                if node_id and bound_node_id and bound_node_id != node_id:
                    logger.warning(
                        "[MonitorModuleIngest] link_conflict identity " "existing_node_id=%s incoming_node_id=%s instance_id=%s",
                        bound_node_id,
                        node_id,
                        by_identity.id,
                    )
                    return IngestResult(
                        id=by_identity.id,
                        conflict=LINK_CONFLICT,
                        created=False,
                        updated=False,
                        claimed=False,
                    ).as_dict()
                existing = by_identity

        if existing:
            source_module = str(params.get("source_module") or "")
            credential = cls._extract_credential(raw) if source_module == "cmdb" else None
            model_id = cls._resolve_cmdb_model_id(raw) if source_module == "cmdb" else ""
            allow_cred = bool(params.get("allow_credential_create"))
            # 默认 False：节点/资产页推送不得突然建监控；仅扫描等显式 allow_credential_create 打开。
            create_enabled = CMDB_CREDENTIAL_CREATE_ENABLED or allow_cred
            if source_module == "cmdb" and not (create_enabled and credential):
                return cls._link_association_ids(
                    existing,
                    node_id=node_id,
                    cmdb_id=cmdb_id,
                    operator=operator,
                )
            has_collect = CollectConfig.objects.filter(monitor_instance_id=existing.id).exists()
            # 已按 cmdb_id/node_id 命中的空壳：扫描带凭据推送仍须补采集，不能只 update。
            needs_cmdb_collect = (
                source_module == "cmdb" and create_enabled and bool(credential) and model_id in CMDB_CREATE_ADAPTED_MODEL_IDS and not has_collect
            )
            if needs_cmdb_collect:
                instance = cls._create_adapted_instance(
                    raw=raw,
                    node_id=node_id,
                    cmdb_id=cmdb_id,
                    credential=credential,
                    operator=operator,
                    allowed_org_ids=allowed,
                    model_id=model_id,
                    actor_context=actor_context,
                )
                return IngestResult(id=instance.id, updated=True).as_dict()

            # 仅扫描带凭据路径：cmdb_id 已关联且已有采集 → 幂等跳过（不影响 node_mgmt / 无凭据 push）。
            if (
                source_module == "cmdb"
                and create_enabled
                and bool(credential)
                and model_id in CMDB_CREATE_ADAPTED_MODEL_IDS
                and by_cmdb is not None
                and existing.id == by_cmdb.id
                and has_collect
            ):
                return IngestResult(id=existing.id, skipped=True).as_dict()

            needs_collect = (
                source_module == "node_mgmt"
                and bool(node_id)
                and not CollectConfig.objects.filter(
                    monitor_instance_id=existing.id,
                    collector=HOST_AGENT_COLLECTOR,
                    collect_type=HOST_AGENT_COLLECT_TYPE,
                ).exists()
            )
            plugin = cls._require_host_agent_plugin() if needs_collect else None
            with transaction.atomic():
                updated = cls._update_instance(
                    existing,
                    raw=raw,
                    node_id=node_id,
                    cmdb_id=cmdb_id,
                    operator=operator,
                    allowed_org_ids=allowed,
                )
                if needs_collect:
                    cls._apply_agent_host_collect(
                        updated,
                        node_id=node_id,
                        raw=raw,
                        allowed_org_ids=allowed,
                        plugin=plugin,
                    )
            return IngestResult(id=updated.id, updated=True).as_dict()

        return cls._create_for_source(
            source_module=str(params.get("source_module") or ""),
            raw=raw,
            node_id=node_id,
            cmdb_id=cmdb_id,
            operator=operator,
            allowed_org_ids=allowed,
            allow_credential_create=bool(params.get("allow_credential_create")),
            actor_context=actor_context,
        )

    @classmethod
    def _link_association_ids(
        cls,
        instance: MonitorInstance,
        *,
        node_id: str | None,
        cmdb_id: str | None,
        operator: str,
    ) -> dict[str, Any]:
        if instance.is_deleted:
            return IngestResult(id=None, ignored=True).as_dict()
        bound_node = cls._normalize_optional_str(instance.node_id)
        bound_cmdb = cls._normalize_optional_str(instance.cmdb_id)
        if node_id and bound_node and bound_node != node_id:
            return IngestResult(id=instance.id, conflict=LINK_CONFLICT, created=False, updated=False, claimed=False).as_dict()
        if cmdb_id and bound_cmdb and bound_cmdb != cmdb_id:
            return IngestResult(id=instance.id, conflict=LINK_CONFLICT, created=False, updated=False, claimed=False).as_dict()
        update_fields: list[str] = []
        claimed = False
        if node_id and bound_node != node_id:
            instance.node_id = node_id
            update_fields.append("node_id")
            claimed = True
        if cmdb_id and bound_cmdb != cmdb_id:
            instance.cmdb_id = cmdb_id
            update_fields.append("cmdb_id")
            claimed = True
        if operator:
            instance.updated_by = operator
            update_fields.append("updated_by")
        if update_fields:
            instance.save(update_fields=update_fields + ["updated_at"])
        return IngestResult(
            id=instance.id,
            created=False,
            updated=not claimed,
            claimed=claimed,
        ).as_dict()

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
        allow_credential_create: bool = False,
        actor_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """未命中任何已有实例时的创建分流。

        统一原则（CMDB → 监控）：
          - 已有实例：只更新建链 / 回填 cmdb_id（本方法不处理）。
          - 创建资产并自动监控：必须同时满足「传了凭据」+「对象在适配范围内」。
          - 无凭据或未适配对象：不创建，仅关联；走到这里说明无可建关系 → ignored。

        当前适配范围：CMDB model_id ∈ CMDB_CREATE_ADAPTED_MODEL_IDS。

        节点管理推送创建：必须命中 Host + Telegraf 主机模板后再创建；套用失败则整次失败。
        """
        if source_module == "cmdb":
            credential = cls._extract_credential(raw)
            model_id = cls._resolve_cmdb_model_id(raw)
            create_enabled = CMDB_CREDENTIAL_CREATE_ENABLED or allow_credential_create
            if not create_enabled or not credential or model_id not in CMDB_CREATE_ADAPTED_MODEL_IDS:
                logger.info(
                    "[MonitorModuleIngest] cmdb push skip create "
                    "(enabled=%s allow=%s credential=%s adapted=%s model_id=%s) "
                    "cmdb_id=%s node_id=%s",
                    CMDB_CREDENTIAL_CREATE_ENABLED,
                    allow_credential_create,
                    bool(credential),
                    model_id in CMDB_CREATE_ADAPTED_MODEL_IDS,
                    model_id,
                    cmdb_id,
                    node_id,
                )
                return IngestResult(id=None, ignored=True).as_dict()

            instance = cls._create_adapted_instance(
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                credential=credential,
                operator=operator,
                allowed_org_ids=allowed_org_ids,
                model_id=model_id,
                actor_context=actor_context,
            )
            return IngestResult(id=instance.id, created=True).as_dict()

        if source_module == "node_mgmt" and node_id:
            if not cls._extract_ip(raw) or cls._extract_cloud_region_id(raw) is None:
                raise ValueError("host ingest from node_mgmt requires ip and cloud")
            plugin = cls._require_host_agent_plugin()
            with transaction.atomic():
                created = cls._create_instance(
                    raw=raw,
                    node_id=node_id,
                    cmdb_id=cmdb_id,
                    operator=operator,
                    allowed_org_ids=allowed_org_ids,
                )
                cls._apply_agent_host_collect(
                    created,
                    node_id=node_id,
                    raw=raw,
                    allowed_org_ids=allowed_org_ids,
                    plugin=plugin,
                )
            return IngestResult(id=created.id, created=True).as_dict()

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
        """从 envelope raw 提取远程采集凭据。

        主机 / 库 / IPMI 需要 username 或 password / 私钥；SNMP v2 允许仅 community；
        Influx 允许仅 token。
        """
        credential = raw.get("credential")
        if not isinstance(credential, dict):
            return None
        username = str(credential.get("username") or credential.get("user") or credential.get("sec_name") or "").strip()
        community = str(credential.get("community") or "").strip()
        token = str(credential.get("token") or "").strip()
        password = str(credential.get("password") or "").strip()
        private_key = str(credential.get("private_key") or credential.get("private_key_content") or "").strip()
        if not any((username, community, token, password, private_key)):
            return None
        return credential

    @classmethod
    def _require_host_agent_plugin(cls):
        """节点推送必须命中 Host + Telegraf/host 插件及其默认模块模板。"""
        from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate

        plugin = MonitorPlugin.objects.filter(
            name=HOST_PLUGIN_NAME,
            collector=HOST_AGENT_COLLECTOR,
            collect_type=HOST_AGENT_COLLECT_TYPE,
        ).first()
        if not plugin:
            raise ValueError(f"host monitor plugin {HOST_PLUGIN_NAME!r} " f"({HOST_AGENT_COLLECTOR}/{HOST_AGENT_COLLECT_TYPE}) not found")
        existing_types = set(MonitorPluginConfigTemplate.objects.filter(plugin=plugin).values_list("type", flat=True))
        missing = [module for module in DEFAULT_HOST_COLLECT_MODULES if module not in existing_types]
        if missing:
            raise ValueError(f"host monitor plugin {HOST_PLUGIN_NAME!r} missing templates: {missing}")
        return plugin

    @classmethod
    def _require_adapted_plugin(cls, model_id: str):
        """带凭据创建必须命中对应 General / Remote 插件名，禁止按对象取 id 最小插件。"""
        from apps.monitor.models import MonitorPlugin

        plugin_name = CMDB_MODEL_TO_MONITOR_PLUGIN.get(model_id)
        if not plugin_name:
            raise ValueError(f"no monitor plugin mapping for model_id={model_id}")
        plugin = MonitorPlugin.objects.filter(name=plugin_name).first()
        if not plugin:
            raise ValueError(f"monitor plugin {plugin_name!r} not found")
        return plugin

    @classmethod
    def _apply_agent_host_collect(
        cls,
        instance: MonitorInstance,
        *,
        node_id: str,
        raw: dict[str, Any],
        allowed_org_ids: list[int],
        plugin,
    ) -> None:
        """为节点推送实例套用 Host + Telegraf 主机模板。失败必须抛出，由调用方回滚。"""
        from apps.monitor.services.node_mgmt import InstanceConfigService

        logical_id = normalize_instance_identity(instance.id)["logical_instance_value"]
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

        InstanceConfigService.create_monitor_instance_by_node_mgmt(
            {
                "monitor_object_id": instance.monitor_object_id,
                "collector": HOST_AGENT_COLLECTOR,
                "collect_type": HOST_AGENT_COLLECT_TYPE,
                "monitor_plugin_id": plugin.id,
                "configs": configs,
                "instances": [
                    {
                        "instance_id": logical_id,
                        "instance_name": instance.name,
                        "node_ids": [node_id],
                        "group_ids": cls._normalize_org_ids(raw, allowed_org_ids),
                        "instance_type": "os",
                    }
                ],
            }
        )

    @classmethod
    def _create_adapted_instance(
        cls,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        credential: dict[str, Any],
        operator: str,
        allowed_org_ids: list[int],
        model_id: str,
        actor_context: dict[str, Any] | None = None,
    ) -> MonitorInstance:
        """CMDB 带凭据创建：按插件名套用接入页同一条创建函数。失败禁止建空壳。"""
        plugin = cls._require_adapted_plugin(model_id)
        if model_id == "host":
            return cls._create_remote_host_instance(
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                credential=credential,
                operator=operator,
                allowed_org_ids=allowed_org_ids,
                plugin=plugin,
                actor_context=actor_context,
            )

        spec = cls._adapted_collect_spec(model_id)
        ip = cls._extract_ip(raw)
        if not ip:
            raise ValueError("remote collect requires raw.ip")

        collector_node_id, cloud = cls._pick_container_node(raw, allowed_org_ids)
        if not collector_node_id:
            raise ValueError("no container collector node available for remote collect")
        if cloud is None:
            cloud = 1

        from apps.monitor.services.node_mgmt import InstanceConfigService

        monitor_object = cls._resolve_monitor_object(raw)
        raw_instance_id = spec["instance_id"](cloud=cloud, ip=ip, raw=raw)
        storage_key = cls._storage_key_after_onboarding(
            model_id=model_id,
            raw_instance_id=raw_instance_id,
            cloud=cloud,
            ip=ip,
        )
        instance = cls._find_by_pk(storage_key)
        # 已有空壳（无采集配置）必须补走接入页；否则只会补链路字段，名称/采集都会缺。
        if instance is None or not CollectConfig.objects.filter(monitor_instance_id=instance.id).exists():
            instance_row: dict[str, Any] = {
                "instance_id": raw_instance_id,
                "instance_name": cls._extract_name(raw, ip=ip),
                "node_ids": [collector_node_id],
                "group_ids": cls._normalize_org_ids(raw, allowed_org_ids),
                "instance_type": spec["instance_type"],
                "ip": ip,
                "cloud_region_id": cloud,
            }
            # 与 Host Remote 同因：插件 fact 常绑 host/server，只传 ip 会报「必需实例事实缺失」。
            cls._fill_instance_fact_ip_fields(instance_row, plugin=plugin, ip=ip)
            InstanceConfigService.create_monitor_instance_by_node_mgmt(
                {
                    "monitor_object_id": monitor_object.id,
                    "collector": plugin.collector or HOST_AGENT_COLLECTOR,
                    "collect_type": plugin.collect_type or spec["collect_type"],
                    "monitor_plugin_id": plugin.id,
                    "configs": [spec["build_config"](ip=ip, raw=raw, credential=credential)],
                    "instances": [instance_row],
                },
                actor_context,
            )
            instance = cls._find_by_pk(storage_key)
        if instance is None:
            raise ValueError("remote onboarding did not create instance")
        update_fields: list[str] = []
        desired_name = cls._extract_name(raw, ip=ip)
        if desired_name and instance.name != desired_name:
            instance.name = desired_name
            update_fields.append("name")
        if cmdb_id and instance.cmdb_id != cmdb_id:
            instance.cmdb_id = cmdb_id
            update_fields.append("cmdb_id")
        if ip and instance.ip != ip:
            instance.ip = ip
            update_fields.append("ip")
        if cloud is not None and instance.cloud_region_id != cloud:
            instance.cloud_region_id = cloud
            update_fields.append("cloud_region_id")
        if update_fields:
            instance.save(update_fields=update_fields + ["updated_at"])
        org_ids = cls._normalize_org_ids(raw, allowed_org_ids)
        cls._bind_organizations(instance, org_ids, operator=operator)
        return instance

    @classmethod
    def _storage_key_after_onboarding(
        cls,
        *,
        model_id: str,
        raw_instance_id: str,
        cloud,
        ip: str,
    ) -> str:
        """创建后反查用的主键：交给监控接入页同一套 identity adapter，扫描侧不另编一套。"""
        from apps.monitor.services.node_mgmt import InstanceConfigService

        object_name = CMDB_MODEL_TO_MONITOR_OBJECT.get(model_id, HOST_OBJECT_NAME)
        instances = [
            {
                "instance_id": raw_instance_id,
                "ip": ip,
                "cloud_region_id": cloud,
            }
        ]
        if InstanceConfigService._should_use_network_device_identity_adapter(object_name):
            prepared = InstanceConfigService._prepare_network_device_identity_instances(instances)
            return prepared[0]["storage_instance_key"]
        if InstanceConfigService._should_use_host_identity_adapter(object_name):
            prepared = InstanceConfigService._prepare_host_identity_instances(instances)
            return prepared[0]["storage_instance_key"]
        return normalize_instance_identity(raw_instance_id)["storage_instance_key"]

    @classmethod
    def _adapted_collect_spec(cls, model_id: str) -> dict[str, Any]:
        if model_id in {"switch", "router", "firewall", "loadbalance"}:
            return {
                "collect_type": "snmp",
                "instance_type": model_id,
                "build_config": lambda **kwargs: cls._build_snmp_config(config_type=model_id, **kwargs),
                "instance_id": lambda *, cloud, ip, raw: f"{cloud}_{model_id}_snmp_{ip}",
            }
        if model_id == "physcial_server":
            return {
                "collect_type": "ipmi",
                "instance_type": "hardware_server",
                "build_config": cls._build_ipmi_config,
                "instance_id": lambda *, cloud, ip, raw: f"{cloud}_hardware_server_ipmi_{ip}",
            }
        db_type = {
            "mysql": "mysql",
            "postgresql": "postgres",
            "mssql": "mssql",
            "influxdb": "influxdb",
        }[model_id]
        default_port = DB_DEFAULT_PORTS.get(db_type, 3306)
        return {
            "collect_type": "database",
            "instance_type": db_type,
            "build_config": lambda **kwargs: cls._build_database_config(db_type=db_type, **kwargs),
            "instance_id": lambda *, cloud, ip, raw: (
                f"{cloud}_{ip}" if db_type == "influxdb" else f"{cloud}_{ip}_{cls._extract_port(raw, default=default_port)}"
            ),
        }

    @classmethod
    def _build_snmp_config(
        cls,
        *,
        ip: str,
        raw: dict[str, Any],
        credential: dict[str, Any],
        config_type: str = "switch",
    ) -> dict[str, Any]:
        version_raw = str(credential.get("version") or raw.get("version") or "2").lower()
        version = 3 if "3" in version_raw else 2
        port = credential.get("snmp_port") or credential.get("port") or raw.get("snmp_port") or raw.get("port") or 161
        config: dict[str, Any] = {
            "type": config_type,
            "ip": ip,
            "port": int(port) if str(port).isdigit() else 161,
            "version": version,
            "interval": DEFAULT_COLLECT_INTERVAL,
            "timeout": DEFAULT_SNMP_TIMEOUT,
        }
        if version == 2:
            config["community"] = str(credential.get("community") or "")
        else:
            config["sec_name"] = str(credential.get("username") or credential.get("sec_name") or "")
            config["sec_level"] = str(credential.get("level") or credential.get("sec_level") or "authNoPriv")
            config["auth_protocol"] = str(credential.get("integrity") or credential.get("auth_protocol") or "sha")
            config["auth_password"] = str(credential.get("authkey") or credential.get("auth_password") or credential.get("password") or "")
            if str(config["sec_level"]).lower() == "authpriv":
                config["priv_protocol"] = str(credential.get("privacy") or credential.get("priv_protocol") or "aes")
                config["priv_password"] = str(credential.get("privkey") or credential.get("priv_password") or "")
        return config

    @classmethod
    def _build_ipmi_config(
        cls,
        *,
        ip: str,
        raw: dict[str, Any],
        credential: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": "hardware_server",
            "monitor_ip": ip,
            "username": str(credential.get("username") or ""),
            "ENV_PASSWORD": str(credential.get("password") or ""),
            "protocol": str(credential.get("protocol") or "lanplus"),
            "interval": DEFAULT_COLLECT_INTERVAL,
            "timeout": DEFAULT_SNMP_TIMEOUT,
        }

    @classmethod
    def _build_database_config(
        cls,
        *,
        db_type: str,
        ip: str,
        raw: dict[str, Any],
        credential: dict[str, Any],
    ) -> dict[str, Any]:
        default_port = DB_DEFAULT_PORTS.get(db_type, 3306)
        port = cls._extract_port(raw, default=credential.get("port") or default_port)
        username = str(credential.get("username") or credential.get("user") or "")
        config: dict[str, Any] = {
            "type": db_type,
            "username": username,
            "ENV_PASSWORD": str(credential.get("password") or credential.get("token") or ""),
            "interval": DEFAULT_COLLECT_INTERVAL,
            "timeout": DEFAULT_SNMP_TIMEOUT,
        }
        if db_type == "influxdb":
            scheme = str(credential.get("scheme") or ("https" if credential.get("ssl") else "http")).strip().lower() or "http"
            if scheme not in ("http", "https"):
                scheme = "http"
            config["server"] = f"{scheme}://{ip}:{port}/debug/vars"
        else:
            config["host"] = ip
            config["port"] = port
        return config

    @staticmethod
    def _extract_port(raw: dict[str, Any], default=None) -> int:
        value = raw.get("port") or raw.get("snmp_port") or default
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(default)
            except (TypeError, ValueError):
                return 0

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
        plugin,
        actor_context: dict[str, Any] | None = None,
    ) -> MonitorInstance:
        """CMDB 带凭据创建：走 Host Remote 远程采集模板。套用失败则整次失败。"""
        ip = cls._extract_ip(raw)
        if not ip:
            raise ValueError("remote collect requires raw.ip")

        collector_node_id, cloud = cls._pick_container_node(raw, allowed_org_ids)
        if not collector_node_id:
            raise ValueError("no container collector node available for remote collect")
        if cloud is None:
            cloud = 1

        from apps.monitor.services.node_mgmt import InstanceConfigService

        monitor_object = cls._resolve_monitor_object(raw)
        raw_instance_id = f"{cloud}_os_{ip}"
        storage_key = cls._storage_key_after_onboarding(
            model_id="host",
            raw_instance_id=raw_instance_id,
            cloud=cloud,
            ip=ip,
        )
        instance = cls._find_by_pk(storage_key)
        if instance is None or not CollectConfig.objects.filter(monitor_instance_id=instance.id).exists():
            InstanceConfigService.create_monitor_instance_by_node_mgmt(
                {
                    "monitor_object_id": monitor_object.id,
                    "collector": plugin.collector or HOST_AGENT_COLLECTOR,
                    "collect_type": plugin.collect_type or HOST_REMOTE_COLLECT_TYPE,
                    "monitor_plugin_id": plugin.id,
                    "configs": [cls._build_remote_host_config(ip=ip, raw=raw, credential=credential)],
                    "instances": [
                        {
                            "instance_id": raw_instance_id,
                            "instance_name": cls._extract_name(raw, ip=ip),
                            "node_ids": [collector_node_id],
                            "group_ids": cls._normalize_org_ids(raw, allowed_org_ids),
                            "instance_type": "os",
                            # Host Remote 插件 fact binding 读 host；接入页其它路径也认 ip。
                            "host": ip,
                            "ip": ip,
                            "cloud_region_id": cloud,
                        }
                    ],
                },
                actor_context,
            )
            instance = cls._find_by_pk(storage_key)
        if instance is None:
            raise ValueError("remote onboarding did not create instance")
        update_fields: list[str] = []
        desired_name = cls._extract_name(raw, ip=ip)
        if desired_name and instance.name != desired_name:
            instance.name = desired_name
            update_fields.append("name")
        linked = node_id
        if not linked:
            linked = cls._best_effort_auto_link_node(monitor_id=instance.id, ip=ip, cloud=cloud)
        if linked and instance.node_id != linked:
            instance.node_id = linked
            update_fields.append("node_id")
        if cmdb_id and instance.cmdb_id != cmdb_id:
            instance.cmdb_id = cmdb_id
            update_fields.append("cmdb_id")
        if ip and instance.ip != ip:
            instance.ip = ip
            update_fields.append("ip")
        if cloud is not None and instance.cloud_region_id != cloud:
            instance.cloud_region_id = cloud
            update_fields.append("cloud_region_id")
        if update_fields:
            instance.save(update_fields=update_fields + ["updated_at"])
        return instance

    @staticmethod
    def _fill_instance_fact_ip_fields(
        instance_row: dict[str, Any],
        *,
        plugin,
        ip: str,
    ) -> None:
        """按插件 instance_fact_bindings 补齐 input/ip 字段（如 host、server），不另开接入路径。"""
        if not ip:
            return
        for binding in getattr(plugin, "instance_fact_bindings", None) or []:
            if not isinstance(binding, dict):
                continue
            if binding.get("resolver") != "input" or binding.get("value_type") != "ip":
                continue
            field = (binding.get("options") or {}).get("field")
            if field and field not in instance_row:
                instance_row[field] = ip

    @classmethod
    def _build_remote_host_config(
        cls,
        *,
        ip: str,
        raw: dict[str, Any],
        credential: dict[str, Any],
    ) -> dict[str, Any]:
        """把扫描/CMDB 凭据映射为 Host Remote 接入页 configs；密钥经 ENV_* 走 env_config。"""
        os_type_raw = str(raw.get("os_type") or raw.get("operating_system") or "").lower()
        os_type = "windows" if "win" in os_type_raw else "linux"

        auth_raw = str(credential.get("auth_type") or credential.get("authType") or "").strip()
        if auth_raw in ("private_key", "privateKey"):
            auth_type = "private_key"
        elif auth_raw:
            auth_type = "password"
        else:
            auth_type = "private_key" if credential.get("private_key") or credential.get("private_key_content") else "password"

        port = credential.get("port") or ""
        try:
            port = int(port) if port not in (None, "") else ""
        except (TypeError, ValueError):
            port = str(port)

        config: dict[str, Any] = {
            "type": HOST_REMOTE_CONFIG_TYPE,
            "interval": DEFAULT_COLLECT_INTERVAL,
            "host": ip,
            "os_type": os_type,
            "username": str(credential.get("username") or credential.get("user") or ""),
            "auth_type": auth_type,
            "port": port,
            "metrics_modules": list(HOST_REMOTE_METRICS_MODULES),
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
                logger.warning("[MonitorModuleIngest] container node lookup failed: %s", exc)
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
        cmdb_aliases: list[str] | None = None,
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
            existing = cls._find_by_cmdb_id(cmdb_id, aliases=cmdb_aliases)

        if not existing:
            logger.info(
                "[MonitorModuleIngest] lifecycle no-op: instance not found " "monitor_id=%s node_id=%s cmdb_id=%s",
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
        return MonitorInstance.objects.filter(id=instance_id).select_related("monitor_object").first()

    @classmethod
    def _find_by_node_id(cls, node_id: str) -> MonitorInstance | None:
        return MonitorInstance.objects.filter(node_id=node_id, is_deleted=False).select_related("monitor_object").first()

    @classmethod
    def _find_by_cmdb_id(
        cls,
        cmdb_id: str,
        *,
        aliases: list[str] | None = None,
    ) -> MonitorInstance | None:
        from apps.cmdb.services.instance_identity import expand_cmdb_id_lookup_candidates

        candidates = expand_cmdb_id_lookup_candidates(cmdb_id, aliases)
        if not candidates:
            return None
        return MonitorInstance.objects.filter(cmdb_id__in=candidates, is_deleted=False).select_related("monitor_object").first()

    @classmethod
    def _find_by_type_identity(cls, raw: dict[str, Any]) -> MonitorInstance | None:
        model_id = cls._resolve_cmdb_model_id(raw)
        object_name = CMDB_MODEL_TO_MONITOR_OBJECT.get(model_id)
        ip = cls._extract_ip(raw)
        if not object_name:
            return None
        cloud = cls._extract_cloud_region_id(raw)
        claimed: MonitorInstance | None = None
        if ip and model_id in cls.IP_PORT_CLAIM_MODELS:
            db_type = {"mysql": "mysql", "postgresql": "postgres", "mssql": "mssql"}[model_id]
            port = cls._extract_port(raw, default=DB_DEFAULT_PORTS.get(db_type))
            storage_key = cls._storage_key_after_onboarding(
                model_id=model_id,
                raw_instance_id=f"{cloud or 0}_{ip}_{port}",
                cloud=cloud if cloud is not None else 0,
                ip=ip,
            )
            by_pk = cls._find_by_pk(storage_key)
            if by_pk and not by_pk.is_deleted and by_pk.monitor_object and by_pk.monitor_object.name == object_name:
                claimed = by_pk
        elif ip and model_id in cls.IP_CLOUD_CLAIM_MODELS:
            if cloud is not None:
                storage_key = cls._storage_key_after_onboarding(
                    model_id=model_id,
                    raw_instance_id=f"{cloud}_{ip}",
                    cloud=cloud,
                    ip=ip,
                )
                by_pk = cls._find_by_pk(storage_key)
                if by_pk and not by_pk.is_deleted and by_pk.monitor_object and by_pk.monitor_object.name == object_name:
                    claimed = by_pk
            if claimed is None:
                qs = MonitorInstance.objects.filter(
                    ip=ip,
                    is_deleted=False,
                    monitor_object__name=object_name,
                ).select_related("monitor_object")
                if cloud is not None:
                    qs = qs.filter(cloud_region_id=cloud)
                matches = list(qs[:2])
                if len(matches) == 1:
                    claimed = matches[0]
                elif matches:
                    # IP 身份歧义：不回落到同名，避免误绑
                    return None
                else:
                    claimed = cls._find_by_encoded_network_identity(object_name, ip=ip, cloud=cloud)
                    if claimed is None:
                        claimed = cls._find_by_unique_network_name(object_name, ip=ip)

        if claimed is not None:
            return claimed

        # 最低优先级：CMDB 实例名与监控实例名精确且唯一匹配（不用 IP 合成名）
        explicit_name = str(raw.get("name") or raw.get("inst_name") or "").strip()
        return cls._find_by_unique_instance_name(object_name, name=explicit_name or None)

    @classmethod
    def _find_by_unique_instance_name(cls, object_name: str, *, name: str | None) -> MonitorInstance | None:
        """按监控对象类型 + 实例名精确认领；同名多条则放弃。"""
        text = str(name or "").strip()
        if not text:
            return None
        matches = list(
            MonitorInstance.objects.filter(
                name=text,
                is_deleted=False,
                monitor_object__name=object_name,
            ).select_related(
                "monitor_object"
            )[:2]
        )
        if len(matches) == 1:
            return matches[0]
        return None

    @classmethod
    def _find_by_encoded_network_identity(
        cls,
        object_name: str,
        *,
        ip: str,
        cloud: int | None,
    ) -> MonitorInstance | None:
        from apps.monitor.services.node_mgmt import InstanceConfigService

        if not InstanceConfigService._should_use_network_device_identity_adapter(object_name):
            return None
        hits: list[MonitorInstance] = []
        candidates = MonitorInstance.objects.filter(
            is_deleted=False,
            monitor_object__name=object_name,
        ).select_related("monitor_object")
        for instance in candidates:
            encoded_cloud, encoded_ip = cls._network_identity_parts(instance)
            if cls._normalize_network_identity_ip(encoded_ip) != ip:
                continue
            if cloud is not None and encoded_cloud is not None and int(encoded_cloud) != int(cloud):
                continue
            hits.append(instance)
            if len(hits) > 1:
                return None
        return hits[0] if hits else None

    @classmethod
    def _find_by_unique_network_name(cls, object_name: str, *, ip: str) -> MonitorInstance | None:
        from apps.monitor.services.node_mgmt import InstanceConfigService

        if not InstanceConfigService._should_use_network_device_identity_adapter(object_name):
            return None
        suffix = object_name.strip().lower()
        names = {ip, f"{ip}-{suffix}"}
        matches = list(
            MonitorInstance.objects.filter(
                name__in=names,
                is_deleted=False,
                monitor_object__name=object_name,
            ).select_related(
                "monitor_object"
            )[:2]
        )
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def _normalize_network_identity_ip(cls, value: str | None) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        match = _IPV4_WITH_OPTIONAL_SUFFIX.fullmatch(text)
        return match.group(1) if match else text

    @classmethod
    def _network_identity_parts(cls, instance: MonitorInstance) -> tuple[int | None, str | None]:
        if instance.ip:
            return instance.cloud_region_id, str(instance.ip)
        try:
            logical = normalize_instance_identity(instance.id)["logical_instance_value"]
        except ValueError:
            return None, None
        padded = logical + "=" * ((4 - len(logical) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        except Exception:
            return None, None
        if ":" not in decoded:
            return None, None
        cloud_part, ip_part = decoded.split(":", 1)
        ip_part = ip_part.strip()
        try:
            encoded_cloud = int(cloud_part)
        except (TypeError, ValueError):
            encoded_cloud = None
        return encoded_cloud, ip_part or None

    @classmethod
    def _find_by_ip_cloud(cls, ip: str, cloud: int) -> MonitorInstance | None:
        return cls._find_by_type_identity({"ip": ip, "cloud_region_id": cloud, "model_id": "host"})

    @classmethod
    def _resolve_monitor_object(cls, raw: dict[str, Any]) -> MonitorObject:
        object_id = raw.get("monitor_object_id")
        if object_id not in (None, ""):
            obj = MonitorObject.objects.filter(id=object_id).first()
            if obj:
                return obj
            raise ValueError(f"monitor_object_id not found: {object_id!r}")

        model_id = cls._resolve_cmdb_model_id(raw)
        object_name = CMDB_MODEL_TO_MONITOR_OBJECT.get(model_id, HOST_OBJECT_NAME)
        obj = MonitorObject.objects.filter(name=object_name).first()
        if obj:
            return obj
        raise ValueError(f"monitor object {object_name!r} not found; provide raw.monitor_object_id or create the monitor object")

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
        cloud = cls._extract_cloud_region_id(raw)
        ip = cls._extract_ip(raw)
        if cloud is not None and ip:
            try:
                return normalize_instance_identity(f"{cloud}_os_{ip}")["storage_instance_key"]
            except ValueError:
                pass
        if node_id:
            try:
                return normalize_instance_identity(node_id)["storage_instance_key"]
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
        existing = set(MonitorInstanceOrganization.objects.filter(monitor_instance=instance).values_list("organization", flat=True))
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
