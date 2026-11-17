from django.core.management.base import BaseCommand

from apps.cmdb.services.instance_shape_repair import reset_scalar_repair
from apps.cmdb.tasks.instance_shape_repair import repair_cmdb_instance_shape
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info


class Command(BaseCommand):
    help = "清掉标量改列表阶段的完成标记，并投递启动后的一次性清洗任务。命令本身不扫描实例。"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只说明将要做的事，不清除完成标记，也不投递任务")
        parser.add_argument("--model", type=str, help="保留参数。清洗按阶段游标处理全部模型，不按单个模型切开")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        only_model = options.get("model")
        if only_model:
            self.stdout.write(self.style.NOTICE(f"收到模型 {only_model}。标量阶段按游标处理全部模型，不能只清一个模型。"))
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run：不清除标量阶段完成标记，也不投递清洗任务。"))
            return

        reset_scalar_repair()
        try:
            repair_cmdb_instance_shape.delay()
        except Exception as exc:
            logger.warning(
                "event=scalar_repair_enqueue_failed failed_stage=enqueue error_type=%s",
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            self.stdout.write(self.style.WARNING(f"标量阶段已重新打开，但任务投递失败（{type(exc).__name__}）。下次启动会再投递。"))
            return
        self.stdout.write(self.style.SUCCESS("已重新打开标量改列表阶段，并投递一次性清洗任务。"))
