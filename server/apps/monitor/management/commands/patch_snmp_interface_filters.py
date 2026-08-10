import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.snmp_interface import DEFAULT_IFTYPE_EXCLUDE, IFTYPE_OID
from apps.monitor.models import CollectConfig
from apps.monitor.utils.config_format import ConfigFormat
from apps.monitor.utils.snmp_ifmib_capability import (
    IFMIBCapabilityResolutionError,
    is_interface_filter_capable_plugin,
    resolve_interface_filter_capability_for_migration,
)
from apps.monitor.utils.snmp_interface_template import (
    get_common_ifmib_table,
    has_managed_ifmib_section,
    is_public_ifmib_table,
)
from apps.rpc.node_mgmt import NodeMgmt

# v6：缺省 tagdrop 仅补「从未配置过滤」的存量；不得覆盖全部采集 / 仅名称白名单等故意清空。
CHECKPOINT_VERSION = 6
IFTYPE_FIELD = {"oid": IFTYPE_OID, "name": "ifType", "is_tag": True}


class SnmpIfmibReconcilePartialError(CommandError):
    """部分 child 内容无效；健康配置已继续处理，但本轮不得标记完成。"""


def _load_checkpoint(checkpoint_path: Path, *, overwrite_default: bool) -> tuple[datetime, str] | None:
    if not checkpoint_path.exists():
        return None
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"Invalid checkpoint file / 断点文件无效: {checkpoint_path}: {exc}") from exc
    if checkpoint.get("version") != CHECKPOINT_VERSION:
        raise CommandError(f"Unsupported checkpoint version / 不支持的断点版本: {checkpoint_path}")
    if bool(checkpoint.get("overwrite_default")) != overwrite_default:
        raise CommandError("Checkpoint options do not match --overwrite-default / 断点参数与 --overwrite-default 不一致")
    cursor = checkpoint.get("cursor")
    if cursor is None:
        return None
    if not isinstance(cursor, dict):
        raise CommandError(f"Invalid checkpoint cursor / 断点游标无效: {checkpoint_path}")
    created_at = parse_datetime(str(cursor.get("created_at") or ""))
    config_id = cursor.get("id")
    if created_at is None or config_id in (None, ""):
        raise CommandError(f"Invalid checkpoint cursor / 断点游标无效: {checkpoint_path}")
    return created_at, str(config_id)


def _save_checkpoint(checkpoint_path: Path, *, cursor: tuple[datetime, str], overwrite_default: bool) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=checkpoint_path.parent,
            prefix=f".{checkpoint_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(
                {
                    "version": CHECKPOINT_VERSION,
                    "cursor": {"created_at": cursor[0].isoformat(), "id": cursor[1]},
                    "overwrite_default": overwrite_default,
                },
                temp_file,
                ensure_ascii=False,
            )
            temp_file.flush()
            os.fsync(temp_file.fileno())
        temp_path.replace(checkpoint_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def is_patchable_snmp_child_config(config, *, capable: bool | None = None) -> bool:
    """Return whether a CollectConfig row should receive IF-MIB filter backfill."""
    collect_type = str(getattr(config, "collect_type", "") or "")
    if not collect_type.startswith("snmp"):
        return False
    if capable is None:
        capable = is_interface_filter_capable_plugin(getattr(config, "monitor_plugin", None))
    return bool(capable)


def _reconcile_common_ifmib_fields(config: dict) -> bool:
    common_table = get_common_ifmib_table()
    common_fields = common_table.get("field") or []
    if not any(field.get("name") == "ifType" for field in common_fields):
        insert_at = next(
            (index + 1 for index, field in enumerate(common_fields) if field.get("name") == "ifDescr"),
            len(common_fields),
        )
        common_fields.insert(insert_at, dict(IFTYPE_FIELD))
    changed = False
    tables = config.get("table")
    if not isinstance(tables, list):
        return False
    public_tables = [table for table in tables if isinstance(table, dict) and is_public_ifmib_table(table)]
    if not public_tables:
        return False
    existing_fields = []
    merged_table = dict(public_tables[0])
    for table in public_tables:
        fields = table.get("field", [])
        if not isinstance(fields, list) or any(not isinstance(field, dict) for field in fields):
            raise ValueError("invalid interface table field: expected an object array")
        existing_fields.extend(fields)
        for key, value in table.items():
            if key != "field" and key not in merged_table:
                merged_table[key] = value
    for key, value in common_table.items():
        if key != "field":
            merged_table[key] = value

    consumed_indexes: set[int] = set()
    reconciled_fields = []
    for common_field in common_fields:
        matched_index = next(
            (
                index
                for index, field in enumerate(existing_fields)
                if index not in consumed_indexes
                and (field.get("name") == common_field.get("name") or field.get("oid") == common_field.get("oid"))
            ),
            None,
        )
        if matched_index is None:
            reconciled_fields.append(dict(common_field))
            continue
        consumed_indexes.add(matched_index)
        reconciled_fields.append({**existing_fields[matched_index], **common_field})
    common_names = {field.get("name") for field in common_fields}
    common_oids = {field.get("oid") for field in common_fields}
    reconciled_fields.extend(
        field
        for index, field in enumerate(existing_fields)
        if index not in consumed_indexes and field.get("name") not in common_names and field.get("oid") not in common_oids
    )
    merged_table["field"] = reconciled_fields

    first_public_index = next(index for index, table in enumerate(tables) if table in public_tables)
    reconciled_tables = [table for table in tables if table not in public_tables]
    reconciled_tables.insert(first_public_index, merged_table)
    if reconciled_tables != tables:
        config["table"] = reconciled_tables
        changed = True
    return changed


def _filter_values_present(value) -> bool:
    return value not in (None, [], "")


def _ensure_default_tagdrop(config: dict, overwrite: bool = False) -> bool:
    """补齐存量缺省排除；已有过滤脚手架或白名单时不得静默改写用户选择。

    模板注释约定：默认排除由页面/创建注入，渲染不做静默 fallback。对账同样遵守：
    - 从未出现 tagexclude/tagpass/tagdrop 的老存量 → 补默认 ifType 排除
    - 「全部采集」或仅 ifDescr 白名单等故意不配 ifType 排除 → 保持原样
    - --overwrite-default 才强制写回产品默认排除
    """
    changed = False
    previously_managed = (
        (isinstance(config.get("tagexclude"), list) and "ifType" in config["tagexclude"])
        or isinstance(config.get("tagpass"), dict)
        or isinstance(config.get("tagdrop"), dict)
    )

    tagexclude = config.get("tagexclude")
    if tagexclude is None:
        config["tagexclude"] = ["ifType"]
        changed = True
    elif "ifType" not in tagexclude:
        tagexclude.append("ifType")
        changed = True

    tagpass = config.get("tagpass") if isinstance(config.get("tagpass"), dict) else {}
    # 任意白名单都表示用户已选「仅采集」策略，不能再塞默认排除。
    if _filter_values_present(tagpass.get("ifType")) or _filter_values_present(tagpass.get("ifDescr")):
        return changed

    tagdrop = config.get("tagdrop")
    if not isinstance(tagdrop, dict):
        tagdrop = {}
    existing = tagdrop.get("ifType")

    if overwrite:
        if existing != DEFAULT_IFTYPE_EXCLUDE:
            tagdrop["ifType"] = list(DEFAULT_IFTYPE_EXCLUDE)
            config["tagdrop"] = tagdrop
            changed = True
        return changed

    if _filter_values_present(existing):
        return changed

    # 已有过滤脚手架（含全部采集清空后的 tagexclude）或仅名称排除：视为故意不配 ifType 排除。
    if previously_managed:
        return changed

    tagdrop["ifType"] = list(DEFAULT_IFTYPE_EXCLUDE)
    config["tagdrop"] = tagdrop
    changed = True
    return changed


def _iter_snmp_input_configs(content: dict) -> list[dict]:
    """返回全部 SNMP input。tagpass 隔离后公共 IF-MIB 可能不在 snmp[0]。"""
    document = content.get("_toml_document") if isinstance(content, dict) else None
    if isinstance(document, dict):
        snmp_inputs = document.get("inputs", {}).get("snmp") if isinstance(document.get("inputs"), dict) else None
        if isinstance(snmp_inputs, list):
            return [item for item in snmp_inputs if isinstance(item, dict)]
        if isinstance(snmp_inputs, dict):
            return [snmp_inputs]
    config = content.get("config") if isinstance(content, dict) else None
    return [config] if isinstance(config, dict) else []


def _validate_snmp_filter_structure(config: dict) -> None:
    expected_filter_types = {
        "tagexclude": list,
        "tagpass": dict,
        "tagdrop": dict,
    }
    for key, expected_type in expected_filter_types.items():
        value = config.get(key)
        if value is not None and not isinstance(value, expected_type):
            raise ValueError(f"invalid {key}: expected {expected_type.__name__}")
        if key == "tagexclude" and isinstance(value, list) and any(not isinstance(item, str) for item in value):
            raise ValueError("invalid tagexclude: expected a string array")
        if key in {"tagpass", "tagdrop"} and isinstance(value, dict):
            if any(
                not isinstance(tag_name, str) or not isinstance(patterns, list) or any(not isinstance(pattern, str) for pattern in patterns)
                for tag_name, patterns in value.items()
            ):
                raise ValueError(f"invalid {key}: expected string-array values")


def _snmp_tables(config: dict) -> list:
    tables = config.get("table")
    if tables is None:
        return []
    if not isinstance(tables, list) or any(not isinstance(table, dict) for table in tables):
        raise ValueError("invalid table: expected an object array")
    return tables


def _public_tables_in_config(config: dict) -> list[dict]:
    return [table for table in _snmp_tables(config) if is_public_ifmib_table(table)]


def _snmp_input_filter_score(config: dict) -> tuple[bool, bool]:
    """优先保留承载接口过滤/仅公共表的 input，便于去掉重复注入。"""
    has_filters = "ifType" in (config.get("tagexclude") or []) or any(
        filter_name in (config.get(filter_key) or {})
        for filter_key in ("tagpass", "tagdrop")
        for filter_name in ("ifType", "ifDescr")
    )
    tables = _snmp_tables(config)
    only_public = bool(tables) and all(is_public_ifmib_table(table) for table in tables)
    return has_filters, only_public


def patch_child_content_dict(content: dict, overwrite_default: bool = False) -> bool:
    if not isinstance(content, dict) or not isinstance(content.get("config"), dict):
        return False

    snmp_configs = _iter_snmp_input_configs(content)
    if not snmp_configs:
        return False

    common_table = get_common_ifmib_table()
    for config in snmp_configs:
        _validate_snmp_filter_structure(config)
        tables = _snmp_tables(config)
        public_tables = [table for table in tables if is_public_ifmib_table(table)]
        if any(
            table.get("name") == common_table.get("name")
            and table.get("oid") in (None, "")
            and table not in public_tables
            for table in tables
        ):
            raise ValueError("ambiguous interface table: public IF-MIB identity cannot be proven")

    public_owners = [config for config in snmp_configs if _public_tables_in_config(config)]
    changed = False

    # tagpass 隔离后公共表常在 snmp[1]；若多处都有，保留过滤承载方并去掉重复公共表。
    if len(public_owners) > 1:
        keep = sorted(public_owners, key=_snmp_input_filter_score, reverse=True)[0]
        for config in public_owners:
            if config is keep:
                continue
            tables = _snmp_tables(config)
            remaining = [table for table in tables if not is_public_ifmib_table(table)]
            if remaining != tables:
                config["table"] = remaining
                changed = True
        public_owners = [keep]

    # capable 且未关闭的缺表存量直接补公共表。enable_ifmib=false 的快照会保留
    # IF-MIB 管理区间标记，由调用方在原始 TOML 上识别并跳过，避免误开启。
    if not public_owners:
        config = content["config"]
        tables = _snmp_tables(config)
        config["table"] = tables
        tables.append(common_table)
        public_owners = [config]
        changed = True

    for config in public_owners:
        changed = _reconcile_common_ifmib_fields(config) or changed
        changed = _ensure_default_tagdrop(config, overwrite=overwrite_default) or changed
    return changed


def _config_has_public_ifmib_table(content: dict) -> bool:
    return any(_public_tables_in_config(config) for config in _iter_snmp_input_configs(content))


def should_skip_closed_ifmib_backfill(raw_content: str | None, content: dict) -> bool:
    """已渲染过 IF-MIB 管理区间且当前无公共表 → 视为实例关闭，禁止回填误开启。"""
    return has_managed_ifmib_section(raw_content) and not _config_has_public_ifmib_table(content)


def _get_keyset_page(queryset, cursor: tuple[datetime, str] | None, batch_size: int):
    page = queryset
    if cursor is not None:
        cursor_created_at, cursor_id = cursor
        page = page.filter(Q(created_at__gt=cursor_created_at) | Q(created_at=cursor_created_at, pk__gt=cursor_id))
    return list(page.order_by("created_at", "pk")[:batch_size])


def _select_patchable_config_ids(configs, capable_by_plugin_id: dict[int | None, bool], *, continue_on_item_error: bool = False):
    config_ids = []
    failed_config_ids = []
    for config in configs:
        plugin = getattr(config, "monitor_plugin", None)
        plugin_id = getattr(plugin, "pk", None)
        if plugin_id not in capable_by_plugin_id:
            try:
                capable_by_plugin_id[plugin_id] = resolve_interface_filter_capability_for_migration(plugin)
            except IFMIBCapabilityResolutionError as exc:
                if continue_on_item_error:
                    failed_config_ids.append(str(config.id))
                    logger.exception(
                        "Skipping SNMP config with unresolved IF-MIB capability / 跳过能力未知的 SNMP 配置: config_id=%s",
                        config.id,
                    )
                    continue
                raise CommandError("Unable to resolve IF-MIB capability / 无法判定 IF-MIB 能力: " f"plugin_id={plugin_id}") from exc
        if is_patchable_snmp_child_config(config, capable=capable_by_plugin_id[plugin_id]):
            config_ids.append(config.id)
    return config_ids, failed_config_ids


def _fetch_complete_child_configs(node_mgmt, config_ids, *, continue_on_missing: bool = False):
    try:
        child_configs = node_mgmt.get_child_configs_by_ids(config_ids) or []
    except Exception as exc:
        logger.error("Failed to fetch SNMP child configs / 获取 SNMP 子配置失败: %s", exc)
        raise
    returned_ids = [str(child.get("id")) for child in child_configs if child.get("id")]
    expected_ids = [str(config_id) for config_id in config_ids]
    missing_ids = sorted(set(expected_ids) - set(returned_ids))
    unexpected_ids = sorted(set(returned_ids) - set(expected_ids))
    if len(returned_ids) != len(set(returned_ids)) or unexpected_ids:
        raise CommandError(
            "NodeMgmt returned an incomplete child-config snapshot / NodeMgmt 返回的子配置快照不完整: " f"missing={missing_ids}, unexpected={unexpected_ids}"
        )
    if missing_ids and not continue_on_missing:
        raise CommandError("NodeMgmt returned an incomplete child-config snapshot / NodeMgmt 返回的子配置快照不完整: " f"missing={missing_ids}, unexpected=[]")
    if missing_ids:
        logger.error("Skipping missing SNMP child configs / 跳过缺失的 SNMP 子配置: %s", missing_ids)
    return child_configs, missing_ids


def _build_pending_updates(child_configs, *, overwrite_default: bool, write_patch, continue_on_item_error: bool = False):
    pending_updates: list[tuple[str, str, str]] = []
    failed_config_ids: list[str] = []
    for child in child_configs:
        config_id = str(child.get("id") or "")
        raw_content = child.get("content")
        if not config_id or not raw_content:
            error = CommandError(f"NodeMgmt returned empty child config content / NodeMgmt 返回空子配置: config_id={config_id}")
            if continue_on_item_error:
                failed_config_ids.append(config_id or "<missing-id>")
                logger.error("Skipping invalid SNMP child config / 跳过无效 SNMP 子配置: %s", error)
                continue
            raise error
        try:
            content = ConfigFormat.toml_to_dict(raw_content)
        except Exception as exc:
            logger.exception("Failed to parse child config / 解析子配置失败 config_id=%s", config_id)
            if continue_on_item_error:
                failed_config_ids.append(config_id)
                continue
            raise CommandError(f"Unable to parse child config / 无法解析子配置: config_id={config_id}: {exc}") from exc
        if should_skip_closed_ifmib_backfill(raw_content, content):
            # 保留用户关闭态；即使仍残留过滤键也不能按证据回填误开启。
            continue
        try:
            changed = patch_child_content_dict(content, overwrite_default=overwrite_default)
        except ValueError as exc:
            if continue_on_item_error:
                failed_config_ids.append(config_id)
                logger.exception("Skipping invalid SNMP child config / 跳过无效 SNMP 子配置: config_id=%s", config_id)
                continue
            raise CommandError("Invalid child config filter structure / 子配置过滤结构无效: " f"config_id={config_id}: {exc}") from exc
        if not changed:
            continue
        try:
            updated_content = ConfigFormat.json_to_toml(content)
        except Exception as exc:
            if continue_on_item_error:
                failed_config_ids.append(config_id)
                logger.exception("Skipping unserializable SNMP child config / 跳过无法序列化的 SNMP 子配置: config_id=%s", config_id)
                continue
            raise CommandError(f"Unable to serialize child config / 无法序列化子配置: config_id={config_id}: {exc}") from exc
        pending_updates.append((config_id, raw_content, updated_content))
        write_patch(f"patch: {config_id}")
    return pending_updates, failed_config_ids


def _apply_pending_updates(node_mgmt, pending_updates, *, compare_and_swap=None):
    if compare_and_swap is None:
        def compare_and_swap(client, config_id, expected, content):
            return client.compare_and_swap_child_config_content_local(
                config_id,
                expected,
                content,
            )
    attempted: list[tuple[str, str, str]] = []
    try:
        for config_id, original_content, updated_content in pending_updates:
            try:
                updated = compare_and_swap(
                    node_mgmt,
                    config_id,
                    original_content,
                    updated_content,
                )
            except Exception:
                # 远端调用异常时无法确定请求是否已提交，必须把当前项纳入条件回滚。
                attempted.append((config_id, original_content, updated_content))
                raise
            if not updated:
                raise CommandError("Concurrent child config change / 子配置发生并发修改: " f"config_id={config_id}")
            attempted.append((config_id, original_content, updated_content))
    except Exception as exc:
        if not attempted:
            raise
        logger.error(
            "Failed to update child config; rolling back attempted configs / " "更新 SNMP 子配置失败，开始回滚已尝试配置 config_id=%s: %s",
            config_id,
            exc,
        )
        attempted_ids = [attempted_id for attempted_id, _, _ in attempted]
        try:
            current_configs, _ = _fetch_complete_child_configs(node_mgmt, attempted_ids)
        except Exception as verify_exc:
            raise CommandError(
                "Unable to verify compensating rollback / 无法校验补偿回滚; " f"uncertain configs / 状态不确定配置: {', '.join(attempted_ids)}"
            ) from verify_exc
        current_content_by_id = {str(child["id"]): child.get("content") or "" for child in current_configs}
        rollback_errors: list[str] = []
        for attempted_id, original_content, updated_content in reversed(attempted):
            current_content = current_content_by_id[attempted_id]
            if current_content == original_content:
                continue
            if current_content != updated_content:
                rollback_errors.append(f"{attempted_id}: concurrent content change")
                continue
            try:
                rolled_back = compare_and_swap(
                    node_mgmt,
                    attempted_id,
                    updated_content,
                    original_content,
                )
                if not rolled_back:
                    rollback_errors.append(f"{attempted_id}: concurrent content change")
            except Exception as rollback_exc:
                rollback_errors.append(f"{attempted_id}: {rollback_exc}")
        if rollback_errors:
            logger.error("Failed to roll back SNMP child configs / 回滚 SNMP 子配置失败: %s", "; ".join(rollback_errors))
            raise CommandError("Compensating rollback failed / 补偿回滚失败; " f"uncertain configs / 状态不确定配置: {'; '.join(rollback_errors)}") from exc
        raise


class Command(BaseCommand):
    help = (
        "Idempotently reconcile the public IF-MIB table and default tagdrop.ifType for existing "
        "IF-MIB-capable SNMP child configs (collect_type snmp / snmp_*); "
        "supports --dry-run and compensating rollback on update failure. Not hooked into startup init. "
        "为具备 IF-MIB 过滤能力的存量 SNMP 子配置（collect_type 为 snmp / snmp_*）幂等补齐公共 IF-MIB 表与默认 tagdrop.ifType；"
        "支持 --dry-run，更新失败时自动补偿回滚。不挂入启动期初始化。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print config_ids that would change only / 只打印将变更的 config_id",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="CollectConfig keyset batch size / CollectConfig 主键游标批次大小（默认 100）",
        )
        parser.add_argument(
            "--checkpoint-file",
            type=Path,
            help="Persist the last successful keyset cursor for resume / 保存最后成功批次游标以便断点续跑",
        )
        parser.add_argument(
            "--overwrite-default",
            action="store_true",
            help=("Reset tagdrop.ifType to the default exclude set even if already set " "(use with care) / 即使已有 tagdrop.ifType 也重置为默认排除集（慎用）"),
        )
        # 仅供同进程运行期补偿任务传入共享断点与租约续期回调；CLI 不暴露 Python 对象参数。
        parser.add_argument("--initial-cursor", help=argparse.SUPPRESS)
        parser.add_argument("--batch-completed", help=argparse.SUPPRESS)
        parser.add_argument("--compare-and-swap", help=argparse.SUPPRESS)
        parser.add_argument("--continue-on-item-error", action="store_true", help=argparse.SUPPRESS)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite_default = options["overwrite_default"]
        batch_size = max(int(options["batch_size"]), 1)
        checkpoint_path = options.get("checkpoint_file") if not dry_run else None
        initial_cursor = options.get("initial_cursor") if not dry_run else None
        batch_completed = options.get("batch_completed") if not dry_run else None
        compare_and_swap = options.get("compare_and_swap") if not dry_run else None
        continue_on_item_error = bool(options.get("continue_on_item_error")) and not dry_run
        if checkpoint_path is not None and initial_cursor is not None:
            raise CommandError("--checkpoint-file cannot be combined with a runtime initial cursor")
        if initial_cursor is not None and (
            not isinstance(initial_cursor, tuple)
            or len(initial_cursor) != 2
            or not isinstance(initial_cursor[0], datetime)
            or initial_cursor[1] in (None, "")
        ):
            raise CommandError("Invalid runtime initial cursor")
        if batch_completed is not None and not callable(batch_completed):
            raise CommandError("Invalid runtime batch-completed callback")
        if compare_and_swap is not None and not callable(compare_and_swap):
            raise CommandError("Invalid runtime compare-and-swap callback")

        # 厂商实例 collect_type 为 snmp_cisco / snmp_h3c 等；精确匹配 "snmp" 会漏补。
        # 同时仅对 IF-MIB 过滤能力插件补齐，避免 hardware_server 被写入默认 tagdrop。
        # 按 plugin_id 缓存能力判定：_is_network_device_snmp_plugin 含 exists()/manifest I/O，
        # 不可对每行 CollectConfig 重复调用（management 命令也会踩 N+1）。
        capable_by_plugin_id: dict[int | None, bool] = {}
        queryset = CollectConfig.objects.filter(
            collect_type__startswith="snmp",
            is_child=True,
        ).select_related("monitor_plugin")

        # 回填是 server 内部运维命令，强制走同进程 AppClient。CAS 写接口不暴露为
        # 远程 NATS handler，避免出现一个无用户/组织上下文的系统级写入口。
        node_mgmt = NodeMgmt(is_local_client=True)
        cursor = _load_checkpoint(checkpoint_path, overwrite_default=overwrite_default) if checkpoint_path is not None else initial_cursor
        scanned_count = 0
        changed_count = 0
        failed_config_ids: list[str] = []
        found_capable = False
        while True:
            configs = _get_keyset_page(queryset, cursor, batch_size)
            if not configs:
                break
            cursor = (configs[-1].created_at, configs[-1].pk)
            scanned_count += len(configs)
            config_ids, selection_failed_ids = _select_patchable_config_ids(
                configs,
                capable_by_plugin_id,
                continue_on_item_error=continue_on_item_error,
            )
            failed_config_ids.extend(selection_failed_ids)
            if not config_ids:
                if checkpoint_path is not None and not failed_config_ids:
                    _save_checkpoint(checkpoint_path, cursor=cursor, overwrite_default=overwrite_default)
                if batch_completed is not None:
                    batch_completed(None if failed_config_ids else cursor)
                continue
            found_capable = True
            child_configs, missing_config_ids = _fetch_complete_child_configs(
                node_mgmt,
                config_ids,
                continue_on_missing=continue_on_item_error,
            )
            failed_config_ids.extend(missing_config_ids)
            pending_updates, batch_failed_config_ids = _build_pending_updates(
                child_configs,
                overwrite_default=overwrite_default,
                write_patch=self.stdout.write,
                continue_on_item_error=continue_on_item_error,
            )
            failed_config_ids.extend(batch_failed_config_ids)
            changed_count += len(pending_updates)
            if not dry_run:
                _apply_pending_updates(node_mgmt, pending_updates, compare_and_swap=compare_and_swap)
                # 文件断点只能指向所有项目均成功的安全前缀。一旦出现毒数据，
                # 即使继续处理后续健康项也不得越过失败位置，否则续跑会永久漏掉它。
                if checkpoint_path is not None and not failed_config_ids:
                    _save_checkpoint(checkpoint_path, cursor=cursor, overwrite_default=overwrite_default)
                if batch_completed is not None:
                    batch_completed(None if failed_config_ids else cursor)

        if failed_config_ids:
            raise SnmpIfmibReconcilePartialError("Some SNMP child configs remain invalid / 部分 SNMP 子配置仍无效: " + ", ".join(failed_config_ids))

        if not found_capable:
            self.stdout.write("No IF-MIB-capable SNMP child configs found / 未发现具备 IF-MIB 过滤能力的 SNMP 子配置")
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Done ({'dry-run' if dry_run else 'applied'}), changed {changed_count}/{scanned_count} / "
                f"完成 ({'dry-run' if dry_run else 'applied'})，变更 {changed_count}/{scanned_count}"
            )
        )
