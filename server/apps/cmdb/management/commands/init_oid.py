# -- coding: utf-8 --
from django.core.management import BaseCommand
from django.core.management.base import CommandError

from apps.cmdb.services.oid_catalog import OidCatalogError, load_oid_catalog, sync_oid_catalog
from apps.core.logger import cmdb_logger as logger


class Command(BaseCommand):
    help = "校验并同步网络设备 SOID 内置映射"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="仅输出差异，不写数据库")
        parser.add_argument(
            "--force", action="store_true", help="兼容参数：重新比较完整目录，不删除数据",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        if options["force"]:
            self.stdout.write(self.style.WARNING("--force 已改为安全全量比较，不会删除内置记录"))
        try:
            entries = load_oid_catalog()
            result = sync_oid_catalog(entries, dry_run=dry_run)
        except OidCatalogError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            logger.error("OID_SYNC_FAILED")
            raise CommandError("OID_SYNC_FAILED") from exc

        prefix = "DRY-RUN " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}SOID同步完成: 新增={result.created}, 更新={result.updated}, "
                f"未变化={result.unchanged}, 用户覆盖={len(result.custom_override_oids)}, "
                f"目录外遗留={len(result.stale_builtin_oids)}"
            )
        )
        if dry_run:
            for entry in result.created_entries:
                self.stdout.write(f"新增 OID {entry.oid}: brand={entry.brand}, model={entry.model}, " f"device_type={entry.device_type}")
            for entry in result.updated_entries:
                self.stdout.write(
                    f"更新 OID {entry.oid}: brand={entry.old_brand} -> {entry.new_brand}, "
                    f"model={entry.old_model} -> {entry.new_model}, "
                    "device_type="
                    f"{entry.old_device_type} -> {entry.new_device_type}"
                )
            for oid in result.custom_override_oids:
                self.stdout.write(f"用户覆盖 OID {oid}")
            for oid in result.stale_builtin_oids:
                self.stdout.write(f"目录外遗留 OID {oid}")
