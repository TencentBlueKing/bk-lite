from django.core.management.base import BaseCommand

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.snmp_interface import DEFAULT_IFTYPE_EXCLUDE, IFTYPE_OID
from apps.monitor.models import CollectConfig
from apps.monitor.utils.config_format import ConfigFormat
from apps.monitor.utils.snmp_ifmib_capability import is_interface_filter_capable_plugin
from apps.rpc.node_mgmt import NodeMgmt


IFTYPE_FIELD = {
    "oid": IFTYPE_OID,
    "name": "ifType",
    "is_tag": True,
}


def is_patchable_snmp_child_config(config, *, capable: bool | None = None) -> bool:
    """Return whether a CollectConfig row should receive IF-MIB filter backfill."""
    collect_type = str(getattr(config, "collect_type", "") or "")
    if not collect_type.startswith("snmp"):
        return False
    if capable is None:
        capable = is_interface_filter_capable_plugin(getattr(config, "monitor_plugin", None))
    return bool(capable)


def _table_has_ifdescr(table: dict) -> bool:
    for field in table.get("field") or []:
        if isinstance(field, dict) and field.get("name") == "ifDescr":
            return True
    return False


def _table_has_iftype(table: dict) -> bool:
    for field in table.get("field") or []:
        if isinstance(field, dict) and (
            field.get("name") == "ifType" or field.get("oid") == IFTYPE_OID
        ):
            return True
    return False


def _config_has_ifdescr(config: dict) -> bool:
    tables = config.get("table")
    return isinstance(tables, list) and any(
        isinstance(table, dict) and _table_has_ifdescr(table) for table in tables
    )


def _ensure_iftype_fields(config: dict) -> bool:
    changed = False
    tables = config.get("table")
    if not isinstance(tables, list):
        return False
    for table in tables:
        if not isinstance(table, dict) or not _table_has_ifdescr(table):
            continue
        if _table_has_iftype(table):
            continue
        fields = table.setdefault("field", [])
        # insert after ifDescr
        insert_at = 0
        for idx, field in enumerate(fields):
            if isinstance(field, dict) and field.get("name") == "ifDescr":
                insert_at = idx + 1
                break
        fields.insert(insert_at, dict(IFTYPE_FIELD))
        changed = True
    return changed


def _ensure_default_tagdrop(config: dict, overwrite: bool = False) -> bool:
    changed = False
    tagexclude = config.get("tagexclude")
    if tagexclude is None:
        config["tagexclude"] = ["ifType"]
        changed = True
    elif "ifType" not in tagexclude:
        tagexclude.append("ifType")
        changed = True
    tagpass = config.get("tagpass")
    if isinstance(tagpass, dict) and tagpass.get("ifType") not in (None, [], ""):
        return changed
    tagdrop = config.get("tagdrop")
    if not isinstance(tagdrop, dict):
        tagdrop = {}
        config["tagdrop"] = tagdrop
        changed = True
    existing = tagdrop.get("ifType")
    if overwrite or existing in (None, [], ""):
        if existing != DEFAULT_IFTYPE_EXCLUDE:
            tagdrop["ifType"] = list(DEFAULT_IFTYPE_EXCLUDE)
            changed = True
    return changed


def patch_child_content_dict(content: dict, overwrite_default: bool = False) -> bool:
    if not isinstance(content, dict) or not isinstance(content.get("config"), dict):
        return False
    config = content["config"]
    if not _config_has_ifdescr(config):
        return False
    tagexclude = config.get("tagexclude")
    if tagexclude is not None and not isinstance(tagexclude, list):
        return False
    changed = _ensure_iftype_fields(config)
    changed = _ensure_default_tagdrop(config, overwrite=overwrite_default) or changed
    return changed


class Command(BaseCommand):
    help = (
        "Idempotently backfill ifType fields and default tagdrop.ifType for existing "
        "IF-MIB-capable SNMP child configs (collect_type snmp / snmp_*); "
        "supports --dry-run and compensating rollback on update failure. Not hooked into startup init. "
        "为具备 IF-MIB 过滤能力的存量 SNMP 子配置（collect_type 为 snmp / snmp_*）幂等补齐 ifType 字段与默认 tagdrop.ifType；"
        "支持 --dry-run，更新失败时自动补偿回滚。不挂入启动期初始化。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print config_ids that would change only / 只打印将变更的 config_id",
        )
        parser.add_argument(
            "--overwrite-default",
            action="store_true",
            help=(
                "Reset tagdrop.ifType to the default exclude set even if already set "
                "(use with care) / 即使已有 tagdrop.ifType 也重置为默认排除集（慎用）"
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite_default = options["overwrite_default"]

        # 厂商实例 collect_type 为 snmp_cisco / snmp_h3c 等；精确匹配 "snmp" 会漏补。
        # 同时仅对 IF-MIB 过滤能力插件补齐，避免 hardware_server 被写入默认 tagdrop。
        config_ids = [
            config.id
            for config in CollectConfig.objects.filter(
                collect_type__startswith="snmp",
                is_child=True,
            ).select_related("monitor_plugin")
            if is_patchable_snmp_child_config(config)
        ]
        if not config_ids:
            self.stdout.write("No SNMP child configs found / 未发现 SNMP 子配置")
            return

        node_mgmt = NodeMgmt()
        try:
            child_configs = node_mgmt.get_child_configs_by_ids(config_ids) or []
        except Exception as exc:
            logger.error("Failed to fetch SNMP child configs / 获取 SNMP 子配置失败: %s", exc)
            raise

        pending_updates: list[tuple[str, str, str]] = []
        for child in child_configs:
            config_id = child.get("id")
            raw_content = child.get("content")
            if not config_id or not raw_content:
                continue
            try:
                content = ConfigFormat.toml_to_dict(raw_content)
            except Exception as exc:
                logger.error(
                    "Failed to parse child config / 解析子配置失败 config_id=%s: %s",
                    config_id,
                    exc,
                )
                continue

            changed = patch_child_content_dict(
                content,
                overwrite_default=overwrite_default,
            )
            if not changed:
                continue

            pending_updates.append((config_id, raw_content, ConfigFormat.json_to_toml(content)))
            self.stdout.write(f"patch: {config_id}")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done (dry-run), changed {len(pending_updates)}/{len(child_configs)} / "
                    f"完成 (dry-run)，变更 {len(pending_updates)}/{len(child_configs)}"
                )
            )
            return

        attempted: list[tuple[str, str]] = []
        try:
            for config_id, original_content, updated_content in pending_updates:
                attempted.append((config_id, original_content))
                node_mgmt.update_child_config_content(config_id, updated_content)
        except Exception as exc:
            logger.error(
                "Failed to update child config; rolling back attempted configs / "
                "更新 SNMP 子配置失败，开始回滚已尝试配置 config_id=%s: %s",
                config_id,
                exc,
            )
            rollback_errors: list[str] = []
            for attempted_id, original_content in reversed(attempted):
                try:
                    node_mgmt.update_child_config_content(attempted_id, original_content)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{attempted_id}: {rollback_exc}")
            if rollback_errors:
                logger.error(
                    "Failed to roll back SNMP child configs / 回滚 SNMP 子配置失败: %s",
                    "; ".join(rollback_errors),
                )
            raise

        self.stdout.write(
            self.style.SUCCESS(
                f"Done (applied), changed {len(pending_updates)}/{len(child_configs)} / "
                f"完成 (applied)，变更 {len(pending_updates)}/{len(child_configs)}"
            )
        )
