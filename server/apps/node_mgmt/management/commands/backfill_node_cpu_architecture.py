from django.core.management import BaseCommand

from apps.core.logger import node_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import ControllerTaskNode, Node
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.installer import exec_command_to_remote


class Command(BaseCommand):
    help = "回填历史节点 CPU 架构"

    def add_arguments(self, parser):
        parser.add_argument("--node-id", action="append", dest="node_ids", default=[], help="指定节点ID，可重复传入")
        parser.add_argument("--limit", type=int, default=100, help="最大回填节点数")
        parser.add_argument("--dry-run", action="store_true", help="仅探测，不写入数据库")

    @staticmethod
    def _detect_command(operating_system: str) -> str | None:
        if operating_system == NodeConstants.LINUX_OS:
            return "uname -m"
        if operating_system == NodeConstants.WINDOWS_OS:
            return "cmd /c echo %PROCESSOR_ARCHITECTURE%"
        return None

    @staticmethod
    def _latest_task_node(node: Node):
        return ControllerTaskNode.objects.filter(ip=node.ip, os=node.operating_system).exclude(username="").order_by("-id").first()

    def handle(self, *args, **options):
        queryset = Node.objects.filter(cpu_architecture="").order_by("id")
        node_ids = options.get("node_ids") or []
        if node_ids:
            queryset = queryset.filter(id__in=node_ids)

        limit = options["limit"]
        if limit > 0:
            queryset = queryset[:limit]

        aes = AESCryptor()
        stats = {"updated": 0, "skipped": 0, "failed": 0}

        for node in queryset:
            detect_command = self._detect_command(node.operating_system)
            if not detect_command:
                stats["skipped"] += 1
                self.stdout.write(self.style.WARNING(f"[skip] {node.id}: unsupported os={node.operating_system}"))
                continue

            task_node = self._latest_task_node(node)
            if not task_node or (not task_node.password and not task_node.private_key):
                stats["skipped"] += 1
                self.stdout.write(self.style.WARNING(f"[skip] {node.id}: no reusable install credentials"))
                continue

            password = aes.decode(task_node.password) if task_node.password else None
            private_key = aes.decode(task_node.private_key) if task_node.private_key else None
            passphrase = aes.decode(task_node.passphrase) if task_node.passphrase else None

            try:
                raw_arch = exec_command_to_remote(
                    task_node.task.work_node,
                    node.ip,
                    task_node.username,
                    password,
                    detect_command,
                    task_node.port,
                    private_key=private_key,
                    passphrase=passphrase,
                )
                normalized_arch = normalize_cpu_architecture(str(raw_arch).strip())
                if not normalized_arch:
                    stats["failed"] += 1
                    self.stdout.write(self.style.ERROR(f"[fail] {node.id}: unable to normalize architecture from '{raw_arch}'"))
                    continue

                if not options["dry_run"]:
                    node.cpu_architecture = normalized_arch
                    node.save(update_fields=["cpu_architecture", "updated_at"])

                stats["updated"] += 1
                self.stdout.write(self.style.SUCCESS(f"[ok] {node.id}: {normalized_arch}"))
            except Exception as error:
                logger.exception(error)
                stats["failed"] += 1
                self.stdout.write(self.style.ERROR(f"[fail] {node.id}: {error}"))

        self.stdout.write(self.style.SUCCESS(f"Backfill finished: updated={stats['updated']} skipped={stats['skipped']} failed={stats['failed']}"))
