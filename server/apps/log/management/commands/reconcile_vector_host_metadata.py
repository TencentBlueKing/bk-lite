import hashlib
from collections import Counter
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.core.logger import log_logger as logger
from apps.log.models import CollectConfig
from apps.log.services.vector_host_metadata import PatchState, VectorHostMetadataPatch
from apps.rpc.node_mgmt import NodeMgmt

SUMMARY_KEYS = (
    "scanned",
    "eligible",
    "current",
    "would_apply",
    "would_revert",
    "applied",
    "reverted",
    "conflict",
    "invalid",
    "cas_conflict",
    "failed",
)
ERROR_KEYS = ("conflict", "invalid", "cas_conflict", "failed")


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_content_hash(content) -> str:
    return _content_hash(content) if isinstance(content, str) else ""


def _get_keyset_page(queryset, cursor: tuple[datetime, str] | None, batch_size: int):
    page = queryset
    if cursor is not None:
        created_at, config_id = cursor
        page = page.filter(Q(created_at__gt=created_at) | Q(created_at=created_at, pk__gt=config_id))
    return list(page.order_by("created_at", "pk")[:batch_size])


def _validate_candidate(config) -> str | None:
    collect_type = config.collect_instance.collect_type
    if collect_type.collector != "Vector" or collect_type.name not in {"file", "docker"}:
        return "log-side collect type ownership mismatch"
    if config.file_type != "toml" or config.is_child is not True:
        return "log-side config role mismatch"
    return None


def _validate_snapshot(config, snapshot: dict) -> str | None:
    expected_collect_type = config.collect_instance.collect_type.name
    if str(snapshot.get("id") or "") != str(config.id):
        return "child snapshot id mismatch"
    if snapshot.get("collect_type") != expected_collect_type or snapshot.get("config_type") != expected_collect_type:
        return "child snapshot collect/config type mismatch"
    if snapshot.get("collector_name") != "Vector" or not snapshot.get("collector_config_id"):
        return "child snapshot parent collector mismatch"
    if not isinstance(snapshot.get("content"), str) or not snapshot["content"]:
        return "child snapshot content is empty"
    return None


class Command(BaseCommand):
    help = (
        "Safely reconcile managed host_name/host_ip enrich blocks for existing Vector file/docker child configs. "
        "Defaults to dry-run; use --apply to write and --revert --apply to remove the exact managed block. "
        "安全补齐或回退 Vector file/docker 存量子配置中的托管主机元数据块；默认仅预检。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist each safe CAS update / 执行逐项 CAS 写入")
        parser.add_argument("--revert", action="store_true", help="Inspect or remove the exact managed v1 block / 检查或删除规范 v1 托管块")
        parser.add_argument("--batch-size", type=int, default=100, help="Stable keyset page size / 稳定游标批次大小（默认 100）")

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        revert = bool(options["revert"])
        batch_size = int(options["batch_size"])
        if batch_size < 1:
            raise CommandError("--batch-size must be greater than zero")

        cursor = None
        queryset = CollectConfig.objects.filter(
            is_child=True,
            file_type="toml",
            collect_instance__collect_type__collector="Vector",
            collect_instance__collect_type__name__in=("file", "docker"),
        ).select_related("collect_instance__collect_type")
        node_mgmt = NodeMgmt(is_local_client=True)
        if not node_mgmt.is_local_client:
            raise CommandError("reconcile requires the local NodeMgmt client")

        stats = Counter({key: 0 for key in SUMMARY_KEYS})
        while True:
            configs = _get_keyset_page(queryset, cursor, batch_size)
            if not configs:
                break
            cursor = (configs[-1].created_at, str(configs[-1].pk))
            stats["scanned"] += len(configs)
            self._process_batch(
                configs,
                node_mgmt=node_mgmt,
                stats=stats,
                apply_changes=apply_changes,
                revert=revert,
            )

        summary = " ".join(f"{key}={stats[key]}" for key in SUMMARY_KEYS)
        self.stdout.write(summary)
        if any(stats[key] for key in ERROR_KEYS):
            raise CommandError("Vector host metadata reconcile did not converge; inspect item statuses and rerun")
        self.stdout.write(self.style.SUCCESS("Vector host metadata reconcile completed"))

    def _process_batch(self, configs, *, node_mgmt, stats, apply_changes: bool, revert: bool) -> None:
        eligible = []
        for config in configs:
            error = _validate_candidate(config)
            if error:
                stats["invalid"] += 1
                self._write_item("invalid", config.id, "", error)
                continue
            stats["eligible"] += 1
            eligible.append(config)

        snapshots_by_id = self._load_snapshots(eligible, node_mgmt=node_mgmt, stats=stats)
        if snapshots_by_id is None:
            return
        for config in eligible:
            self._process_config(
                config,
                snapshots_by_id.get(str(config.id)),
                node_mgmt=node_mgmt,
                stats=stats,
                apply_changes=apply_changes,
                revert=revert,
            )

    def _load_snapshots(self, configs, *, node_mgmt, stats) -> dict | None:
        if not configs:
            return {}
        expected_ids = {str(config.id) for config in configs}
        try:
            snapshots = node_mgmt.get_child_configs_by_ids([config.id for config in configs]) or []
        except Exception as exc:
            logger.exception("Failed to fetch Vector child config snapshots")
            stats["failed"] += len(configs)
            for config in configs:
                self._write_item("failed", config.id, "", f"snapshot fetch failed: {type(exc).__name__}: {exc}")
            return None

        returned_ids = [str(snapshot.get("id") or "") for snapshot in snapshots if isinstance(snapshot, dict)]
        if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) - expected_ids:
            stats["failed"] += len(configs)
            for config in configs:
                self._write_item("failed", config.id, "", "snapshot batch contains duplicate or unexpected ids")
            return None
        return {str(snapshot["id"]): snapshot for snapshot in snapshots if isinstance(snapshot, dict) and snapshot.get("id")}

    def _process_config(self, config, snapshot, *, node_mgmt, stats, apply_changes: bool, revert: bool) -> None:
        if snapshot is None:
            stats["invalid"] += 1
            self._write_item("invalid", config.id, "", "child snapshot is missing")
            return
        snapshot_error = _validate_snapshot(config, snapshot)
        if snapshot_error:
            stats["invalid"] += 1
            self._write_item("invalid", config.id, _safe_content_hash(snapshot.get("content")), snapshot_error)
            return

        original_content = snapshot["content"]
        content_hash = _content_hash(original_content)
        patch_method = VectorHostMetadataPatch.revert if revert else VectorHostMetadataPatch.apply
        try:
            result = patch_method(
                original_content,
                collect_type=config.collect_instance.collect_type.name,
                config_id=str(config.id),
                instance_id=str(config.collect_instance_id),
            )
        except Exception as exc:
            stats["failed"] += 1
            logger.exception("Vector host metadata patch failed: config_id=%s", config.id)
            self._write_item("failed", config.id, content_hash, f"{type(exc).__name__}: {exc}")
            return

        if result.state is PatchState.UNMANAGED_CONFLICT:
            stats["conflict"] += 1
            self._write_item("conflict", config.id, content_hash, result.reason)
            return
        if result.state in {PatchState.INVALID, PatchState.MANAGED_DRIFT}:
            stats["invalid"] += 1
            self._write_item("invalid", config.id, content_hash, result.reason)
            return
        if not result.changed:
            stats["current"] += 1
            self._write_item("current", config.id, content_hash, "")
            return
        if not apply_changes:
            action = "would_revert" if revert else "would_apply"
            stats[action] += 1
            self._write_item(action, config.id, content_hash, "")
            return

        try:
            updated = node_mgmt.compare_and_swap_child_config_content_local(config.id, original_content, result.content)
        except Exception as exc:
            stats["failed"] += 1
            logger.exception("Vector host metadata CAS failed: config_id=%s", config.id)
            self._write_item("failed", config.id, content_hash, f"{type(exc).__name__}: {exc}")
            return
        if not updated:
            stats["cas_conflict"] += 1
            self._write_item("cas_conflict", config.id, content_hash, "concurrent content change")
            return
        action = "reverted" if revert else "applied"
        stats[action] += 1
        self._write_item(action, config.id, _content_hash(result.content), "")

    def _write_item(self, status: str, config_id, content_hash: str, reason: str) -> None:
        fields = [f"status={status}", f"config_id={config_id}"]
        if content_hash:
            fields.append(f"content_sha256={content_hash}")
        if reason:
            fields.append(f"reason={reason}")
        self.stdout.write(" ".join(fields))
