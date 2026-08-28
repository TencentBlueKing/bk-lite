from django.core.management.base import BaseCommand, CommandError

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Material, WikiKnowledgeBase
from apps.opspilot.services.wiki.material_build_queue_service import QUEUED_STATUS, MaterialBuildQueueError, resume_kb_material_builds

_STUCK_STATUSES = frozenset({"parsing", "building", QUEUED_STATUS})


class Command(BaseCommand):
    help = "Celery/进程中断后继续知识库资料构建。" "仅在 worker 已停止、资料卡在排队/解析/构建时使用；正常构建时不要执行。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--knowledge-base",
            action="append",
            type=int,
            dest="knowledge_base_ids",
            help="知识库 ID，可重复指定",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="resume_all",
            help="处理所有仍有排队/解析中/构建中资料的知识库",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只列出将处理的知识库，不改队列、不 kick",
        )
        parser.add_argument(
            "--operator",
            default="ops-cli",
            help="写入构建记录的操作者，默认 ops-cli",
        )

    def handle(self, *args, **options):
        requested_ids = list(options.get("knowledge_base_ids") or [])
        resume_all = bool(options.get("resume_all"))
        if bool(requested_ids) == resume_all:
            raise CommandError("必须指定 --knowledge-base 或 --all 之一")

        if resume_all:
            kb_ids = list(
                Material.objects.filter(status__in=_STUCK_STATUSES)
                .values_list("knowledge_base_id", flat=True)
                .distinct()
                .order_by("knowledge_base_id")
            )
        else:
            kb_ids = requested_ids
            missing = set(kb_ids) - set(WikiKnowledgeBase.objects.filter(pk__in=kb_ids).values_list("pk", flat=True))
            if missing:
                raise CommandError("知识库不存在: %s" % ",".join(str(item) for item in sorted(missing)))

        if not kb_ids:
            self.stdout.write("没有卡在排队/解析中/构建中的资料")
            return

        dry_run = bool(options.get("dry_run"))
        operator = options.get("operator") or "ops-cli"
        for kb_id in kb_ids:
            stuck = Material.objects.filter(knowledge_base_id=kb_id, status__in=_STUCK_STATUSES).count()
            if dry_run:
                self.stdout.write(f"dry-run kb={kb_id} stuck={stuck}")
                continue
            try:
                result = resume_kb_material_builds(kb_id, operator=operator)
            except MaterialBuildQueueError as error:
                raise CommandError(f"kb={kb_id} {error.message}") from error
            except Exception as exc:
                logger.exception("wiki material builds resume command failed kb=%s", kb_id)
                raise CommandError(f"kb={kb_id} 任务投递失败") from exc
            requeued = len(result.get("requeued") or [])
            released = bool(result.get("released"))
            kicked = bool(result.get("kicked"))
            logger.info(
                "wiki material builds resume command kb=%s requeued=%s released=%s kicked=%s",
                kb_id,
                requeued,
                released,
                kicked,
            )
            self.stdout.write(f"kb={kb_id} requeued={requeued} released={int(released)} kicked={int(kicked)}")
