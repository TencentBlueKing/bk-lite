from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.system_mgmt.models import Group
from apps.workflow_orchestration.services.builtin_workflows import ensure_builtin_health_workflows


class Command(BaseCommand):
    help = "按团队幂等初始化 Windows/Linux 内置主机巡检流程"

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, action="append", dest="team_ids", help="指定团队；可重复。省略则处理全部组织")
        parser.add_argument("--username", default="admin", help="内置流程创建人用户名")
        parser.add_argument("--domain", default="domain.com")
        parser.add_argument("--channel-id", type=int, default=1, help="通知原子默认渠道 ID")
        parser.add_argument("--skip-conductor", action="store_true", help="跳过 Conductor 注册（仅写库）")

    def handle(self, *args, **options):
        username = str(options["username"]).strip()
        domain = str(options["domain"]).strip()
        channel_id = int(options["channel_id"])
        user = get_user_model().objects.filter(username=username, domain=domain).first()
        if user is None:
            raise CommandError(f"找不到用户: {username}@{domain}")

        team_ids = options.get("team_ids") or list(Group.objects.filter(parent_id=0).values_list("id", flat=True))
        if not team_ids:
            self.stdout.write(self.style.WARNING("没有可初始化的组织，已跳过"))
            return

        total = 0
        for team_id in team_ids:
            workflows = ensure_builtin_health_workflows(
                team_id=int(team_id),
                username=username,
                domain=domain,
                channel_id=channel_id,
                register_conductor=not options["skip_conductor"],
            )
            total += len(workflows)
            self.stdout.write(f"团队 {team_id}: 已确保 {len(workflows)} 条内置巡检流程")
        self.stdout.write(self.style.SUCCESS(f"内置巡检初始化完成，共处理 {total} 条流程记录"))
