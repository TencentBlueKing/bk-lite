"""审计并可选治理存量定时任务的团队边界。"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.job_mgmt.models import ScheduledTask
from apps.job_mgmt.services.scheduled_task_authz import (
    disable_scheduled_task_and_schedule,
    plan_scheduled_task_team_migration,
)


class Command(BaseCommand):
    help = "只读审计存量定时任务团队边界；显式传 --apply 后归一唯一任务并禁用其余任务"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="应用审计结果；默认只读，不修改任何任务")
        parser.add_argument(
            "--backup-confirmed",
            action="store_true",
            help="确认已保存数据库备份和本命令的只读审计输出；仅 --apply 使用",
        )
        parser.add_argument("--start-after-id", type=int, default=0, help="从指定任务 ID 之后继续，作为稳定恢复游标")
        parser.add_argument("--limit", type=int, help="本次最多处理的任务数；--apply 时必须显式设置正数")

    def handle(self, *args, **options):
        should_apply = options["apply"]
        backup_confirmed = options["backup_confirmed"]
        start_after_id = options["start_after_id"]
        limit = options["limit"]
        if start_after_id < 0:
            raise CommandError("--start-after-id 不能小于 0")
        if limit is not None and limit <= 0:
            raise CommandError("--limit 必须是正数")
        if should_apply and not backup_confirmed:
            raise CommandError("--apply 前必须保存数据库备份和只读审计输出，并传入 --backup-confirmed")
        if should_apply and limit is None:
            raise CommandError("--apply 必须显式传入正数 --limit，避免无界批量变更")
        counts = {"keep": 0, "normalize": 0, "disable": 0}

        tasks = ScheduledTask.objects.select_related("script", "playbook").filter(id__gt=start_after_id).order_by("id")
        if limit is not None:
            tasks = tasks[:limit]
        last_processed_id = start_after_id
        for task in tasks.iterator():
            if should_apply:
                with transaction.atomic():
                    task = ScheduledTask.objects.select_for_update().get(id=task.id)
                    plan = plan_scheduled_task_team_migration(task, lock_resources=True)
                    if plan.action == "normalize":
                        ScheduledTask.objects.filter(id=task.id).update(team=[plan.team])
                    elif plan.action == "disable" and not disable_scheduled_task_and_schedule(task.id):
                        raise CommandError(f"task={task.id} Beat 调度禁用失败，任务状态已回滚；请修复后重试")
            else:
                plan = plan_scheduled_task_team_migration(task)

            counts[plan.action] += 1
            team_text = str(plan.team) if plan.team is not None else "-"
            self.stdout.write(
                f"task={task.id} action={plan.action} team={team_text} "
                f"previous_team={task.team} previous_enabled={task.is_enabled} reason={plan.reason}"
            )
            last_processed_id = task.id

        mode = "APPLY" if should_apply else "DRY-RUN"
        has_more = ScheduledTask.objects.filter(id__gt=last_processed_id).exists()
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} keep={counts['keep']} normalize={counts['normalize']} disable={counts['disable']} "
                f"last_processed_id={last_processed_id} has_more={str(has_more).lower()}"
            )
        )
