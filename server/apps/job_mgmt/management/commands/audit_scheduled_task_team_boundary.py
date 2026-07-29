"""审计并可选治理存量定时任务的团队边界。"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.job_mgmt.models import ScheduledTask
from apps.job_mgmt.services.scheduled_task_authz import plan_scheduled_task_team_migration
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService


class Command(BaseCommand):
    help = "只读审计存量定时任务团队边界；显式传 --apply 后归一唯一任务并禁用其余任务"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="应用审计结果；默认只读，不修改任何任务")

    def handle(self, *args, **options):
        should_apply = options["apply"]
        counts = {"keep": 0, "normalize": 0, "disable": 0}

        tasks = ScheduledTask.objects.select_related("script", "playbook").order_by("id")
        for task in tasks.iterator():
            plan = plan_scheduled_task_team_migration(task)
            counts[plan.action] += 1
            team_text = str(plan.team) if plan.team is not None else "-"
            self.stdout.write(f"task={task.id} action={plan.action} team={team_text} reason={plan.reason}")

            if not should_apply or plan.action == "keep":
                continue

            with transaction.atomic():
                if plan.action == "normalize":
                    ScheduledTask.objects.filter(id=task.id).update(team=[plan.team])
                elif plan.action == "disable":
                    ScheduledTask.objects.filter(id=task.id, is_enabled=True).update(is_enabled=False)

            if plan.action == "disable":
                ScheduledTaskService.toggle_periodic_task(task.id, False)

        mode = "APPLY" if should_apply else "DRY-RUN"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} keep={counts['keep']} normalize={counts['normalize']} disable={counts['disable']}"
            )
        )
