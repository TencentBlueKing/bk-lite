import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.node_mgmt.services.collector_release.constants import CollectorReleaseConstants as C
from apps.node_mgmt.services.collector_release.export import build_release_zip
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class Command(BaseCommand):
    help = "从内置插件目录与 Collector JSON 导出分层探针发行包 zip"

    def add_arguments(self, parser):
        parser.add_argument("--collector", required=True, help="采集器名称，例如 Kafka-Exporter")
        parser.add_argument(
            "--pack-version",
            dest="pack_version",
            required=True,
            help="发行版本，必须是 x.y.z（不用 --version，避免和 Django 命令冲突）",
        )
        parser.add_argument("--output", required=True, help="输出 zip 路径")
        parser.add_argument(
            "--artifact",
            action="append",
            default=[],
            help="二进制，格式 os/arch=/path/to/file，可重复。例如 linux/x86_64=/tmp/kafka_exporter",
        )

    def handle(self, *args, **options):
        version = options["pack_version"]
        if not re.match(C.VERSION_PATTERN, version):
            raise CommandError("version 必须是 x.y.z")
        artifacts = {}
        for item in options["artifact"]:
            if "=" not in item:
                raise CommandError(f"--artifact 格式无效: {item}")
            spec, path = item.split("=", 1)
            if "/" not in spec:
                raise CommandError(f"--artifact 架构格式无效: {spec}")
            os_name, arch = spec.split("/", 1)
            os_name = os_name.strip().lower()
            arch = normalize_cpu_architecture(arch.strip())
            file_path = Path(path)
            if not file_path.exists():
                raise CommandError(f"二进制不存在: {file_path}")
            artifacts[(os_name, arch)] = file_path
        if not artifacts:
            raise CommandError("至少提供一个 --artifact os/arch=/path")
        try:
            payload = build_release_zip(
                collector=options["collector"],
                version=version,
                artifacts=artifacts,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        self.stdout.write(self.style.SUCCESS(f"已写出 {output} ({len(payload)} bytes)"))
