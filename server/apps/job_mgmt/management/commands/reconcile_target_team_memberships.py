from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.job_mgmt.models import Target, TargetTeamMembership
from apps.job_mgmt.models.target import _replace_target_team_memberships
from apps.job_mgmt.utils.team_authz import normalize_authorized_team_ids, normalize_team


def _team_ids(team):
    return normalize_team(team) | normalize_authorized_team_ids(team if isinstance(team, list) else [team])


class Command(BaseCommand):
    help = "校验或修复 Target.team 与可索引团队授权投影的差异"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="修复发现的投影差异；默认仅检查")
        parser.add_argument("--check", action="store_true", help="仅检查；发现差异时返回非零状态")
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        if options["apply"] and options["check"]:
            raise CommandError("--apply 与 --check 不能同时使用")
        batch_size = options["batch_size"]
        if batch_size < 1 or batch_size > 5000:
            raise CommandError("--batch-size 范围为 1-5000")

        apply_changes = options["apply"]
        cursor = 0
        drift_count = 0
        while True:
            with transaction.atomic():
                queryset = Target.objects.filter(id__gt=cursor).order_by("id")
                if apply_changes:
                    queryset = queryset.select_for_update()
                targets = list(queryset.only("id", "team")[:batch_size])
                if not targets:
                    break
                target_ids = [target.id for target in targets]
                actual = {target_id: set() for target_id in target_ids}
                for target_id, team_id in TargetTeamMembership.objects.filter(target_id__in=target_ids).values_list("target_id", "team_id"):
                    actual[target_id].add(team_id)
                drifted = [target for target in targets if actual[target.id] != _team_ids(target.team)]
                drift_count += len(drifted)
                if apply_changes and drifted:
                    _replace_target_team_memberships((target.id, target.team) for target in drifted)
                cursor = targets[-1].id

        if drift_count and not apply_changes:
            raise CommandError(f"发现 {drift_count} 个目标的团队授权投影不一致")
        action = "修复" if apply_changes else "检查"
        self.stdout.write(self.style.SUCCESS(f"团队授权投影{action}完成，差异数: {drift_count}"))
