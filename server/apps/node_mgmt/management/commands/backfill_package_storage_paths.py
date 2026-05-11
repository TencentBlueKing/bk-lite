from io import BytesIO

from asgiref.sync import async_to_sync
from django.core.management import BaseCommand
from nats.js.errors import ObjectNotFoundError

from apps.node_mgmt.models import PackageVersion
from apps.node_mgmt.services.package import PackageService
from apps.rpc.jetstream import JetStreamService


class Command(BaseCommand):
    help = "回填历史包对象路径到带架构的新路径"

    def add_arguments(self, parser):
        parser.add_argument("--type", dest="package_type", default="", help="过滤包类型")
        parser.add_argument("--os", dest="os_name", default="", help="过滤操作系统")
        parser.add_argument("--object", dest="object_name", default="", help="过滤对象名称")
        parser.add_argument("--package-version", dest="package_version", default="", help="过滤版本号")
        parser.add_argument("--cpu_architecture", dest="cpu_architecture", default="", help="过滤 CPU 架构")
        parser.add_argument("--apply", action="store_true", help="执行复制；默认仅预览")

    @staticmethod
    async def _copy_legacy_to_primary(package_obj):
        primary_path = PackageService.build_file_path(package_obj)
        legacy_path = PackageService.build_legacy_file_path(package_obj)
        jetstream = JetStreamService()
        await jetstream.connect()
        try:
            try:
                await jetstream.object_store.get_info(primary_path)
                return "primary_exists", primary_path, legacy_path
            except ObjectNotFoundError:
                pass

            legacy_object = await jetstream.object_store.get(legacy_path)
            await jetstream.put(primary_path, legacy_object.data, description=legacy_object.info.description)
            return "copied", primary_path, legacy_path
        finally:
            await jetstream.close()

    @staticmethod
    async def _inspect_paths(package_obj):
        primary_path = PackageService.build_file_path(package_obj)
        legacy_path = PackageService.build_legacy_file_path(package_obj)
        jetstream = JetStreamService()
        await jetstream.connect()
        try:
            primary_exists = True
            legacy_exists = True
            try:
                await jetstream.object_store.get_info(primary_path)
            except ObjectNotFoundError:
                primary_exists = False
            try:
                await jetstream.object_store.get_info(legacy_path)
            except ObjectNotFoundError:
                legacy_exists = False
            return primary_exists, legacy_exists, primary_path, legacy_path
        finally:
            await jetstream.close()

    def handle(self, *args, **options):
        queryset = PackageVersion.objects.all().order_by("type", "os", "object", "version", "cpu_architecture")
        if options["package_type"]:
            queryset = queryset.filter(type=options["package_type"])
        if options["os_name"]:
            queryset = queryset.filter(os=options["os_name"])
        if options["object_name"]:
            queryset = queryset.filter(object=options["object_name"])
        if options["package_version"]:
            queryset = queryset.filter(version=options["package_version"])
        if options["cpu_architecture"]:
            queryset = queryset.filter(cpu_architecture=options["cpu_architecture"])

        stats = {"copied": 0, "missing": 0, "already_ok": 0}
        apply_changes = options["apply"]

        for package_obj in queryset:
            primary_exists, legacy_exists, primary_path, legacy_path = async_to_sync(self._inspect_paths)(package_obj)
            if primary_exists:
                stats["already_ok"] += 1
                self.stdout.write(self.style.SUCCESS(f"[ok] {package_obj.id}: {primary_path}"))
                continue

            if not legacy_exists:
                stats["missing"] += 1
                self.stdout.write(self.style.WARNING(f"[missing] {package_obj.id}: primary={primary_path} legacy={legacy_path}"))
                continue

            if not apply_changes:
                self.stdout.write(self.style.WARNING(f"[dry-run] {package_obj.id}: copy {legacy_path} -> {primary_path}"))
                continue

            status, _, _ = async_to_sync(self._copy_legacy_to_primary)(package_obj)
            if status in {"copied", "primary_exists"}:
                stats["copied"] += 1
                self.stdout.write(self.style.SUCCESS(f"[copied] {package_obj.id}: {legacy_path} -> {primary_path}"))

        self.stdout.write(
            self.style.SUCCESS(f"Backfill finished: copied={stats['copied']} already_ok={stats['already_ok']} missing={stats['missing']}")
        )
