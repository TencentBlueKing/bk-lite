"""为存量 Wiki 知识库补齐冻结六根并回填简介。"""

from django.core.management.base import BaseCommand, CommandError

from apps.opspilot.services.wiki.frozen_structure_migration_service import ensure_all_frozen_structures
from apps.opspilot.services.wiki.structure_service import StructureServiceError


class Command(BaseCommand):
    help = "为存量 Wiki 知识库补齐冻结根目录，并把空简介从旧 Purpose 回填"

    def add_arguments(self, parser):
        parser.add_argument(
            "--knowledge-base-ids",
            nargs="*",
            type=int,
            default=None,
            dest="knowledge_base_ids",
            help="仅处理指定知识库；缺省处理全部",
        )
        parser.add_argument(
            "--operator",
            type=str,
            default="system",
            help="操作人标识",
        )

    def handle(self, *args, **options):
        try:
            results = ensure_all_frozen_structures(
                operator=options.get("operator") or "system",
                knowledge_base_ids=options.get("knowledge_base_ids"),
            )
        except StructureServiceError as error:
            raise CommandError(f"{error.code}: {error}") from error
        changed = sum(1 for item in results if item.get("changed"))
        failed = [item for item in results if item.get("error")]
        self.stdout.write(f"processed={len(results)} changed={changed} failed={len(failed)}")
        for item in failed:
            self.stderr.write(f"kb={item['knowledge_base_id']} error={item['error']}")
