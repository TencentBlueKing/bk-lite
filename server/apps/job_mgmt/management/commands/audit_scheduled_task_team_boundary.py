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

    def handle(self, *args, **options):
        should_apply = options["apply"]
        counts = {"keep": 0, "normalize": 0, "disable": 0}

        tasks = ScheduledTask.objects.select_related("script", "playbook").order_by("id")
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

        mode = "APPLY" if should_apply else "DRY-RUN"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} keep={counts['keep']} normalize={counts['normalize']} disable={counts['disable']}"
            )
        )
