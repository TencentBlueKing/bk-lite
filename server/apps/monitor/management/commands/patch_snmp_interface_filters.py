from django.core.management.base import BaseCommand

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.snmp_interface import DEFAULT_IFTYPE_EXCLUDE, IFTYPE_OID
from apps.monitor.models import CollectConfig
from apps.monitor.utils.config_format import ConfigFormat
from apps.rpc.node_mgmt import NodeMgmt


IFTYPE_FIELD = {
    "oid": IFTYPE_OID,
    "name": "ifType",
    "is_tag": True,
}


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
    if config.get("tagexclude") != ["ifType"]:
        config["tagexclude"] = ["ifType"]
        changed = True
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


def _remove_filters(config: dict) -> bool:
    changed = False
    if "tagexclude" in config:
        config.pop("tagexclude", None)
        changed = True
    for table_name in ("tagpass", "tagdrop"):
        if table_name in config:
            config.pop(table_name, None)
            changed = True
    tables = config.get("table")
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue
            fields = table.get("field")
            if not isinstance(fields, list):
                continue
            new_fields = [
                field
                for field in fields
                if not (
                    isinstance(field, dict)
                    and (field.get("name") == "ifType" or field.get("oid") == IFTYPE_OID)
                )
            ]
            if len(new_fields) != len(fields):
                table["field"] = new_fields
                changed = True
    return changed


def patch_child_content_dict(content: dict, revert: bool = False, overwrite_default: bool = False) -> bool:
    if not isinstance(content, dict) or not isinstance(content.get("config"), dict):
        return False
    config = content["config"]
    if revert:
        return _remove_filters(config)
    changed = _ensure_iftype_fields(config)
    changed = _ensure_default_tagdrop(config, overwrite=overwrite_default) or changed
    return changed


class Command(BaseCommand):
    help = (
        "Idempotently backfill ifType fields and default tagdrop.ifType for existing SNMP child configs; "
        "supports --dry-run / --revert. Not hooked into startup init. "
        "为存量 SNMP 子配置幂等补齐 ifType 字段与默认 tagdrop.ifType；"
        "支持 --dry-run / --revert。不挂入启动期初始化。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print config_ids that would change only / 只打印将变更的 config_id",
        )
        parser.add_argument(
            "--revert",
            action="store_true",
            help="Remove injected ifType fields and filter blocks / 移除注入的 ifType 与过滤段",
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
        revert = options["revert"]
        overwrite_default = options["overwrite_default"]

        config_ids = list(
            CollectConfig.objects.filter(collect_type="snmp", is_child=True).values_list("id", flat=True)
        )
        if not config_ids:
            self.stdout.write("No SNMP child configs found / 未发现 SNMP 子配置")
            return

        node_mgmt = NodeMgmt()
        try:
            child_configs = node_mgmt.get_child_configs_by_ids(config_ids) or []
        except Exception as exc:
            logger.error("Failed to fetch SNMP child configs / 获取 SNMP 子配置失败: %s", exc)
            raise

        updated = 0
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
                revert=revert,
                overwrite_default=overwrite_default,
            )
            if not changed:
                continue

            summary = "revert" if revert else "patch"
            self.stdout.write(f"{summary}: {config_id}")
            if dry_run:
                updated += 1
                continue
            try:
                node_mgmt.update_child_config_content(
                    config_id,
                    ConfigFormat.json_to_toml(content),
                )
                updated += 1
            except Exception as exc:
                logger.error(
                    "Failed to update child config / 更新子配置失败 config_id=%s: %s",
                    config_id,
                    exc,
                )

        mode = "dry-run" if dry_run else "applied"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done ({mode}), changed {updated}/{len(child_configs)} / "
                f"完成 ({mode})，变更 {updated}/{len(child_configs)}"
            )
        )
