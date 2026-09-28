from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.workflow_orchestration.management.commands.seed_workflow_orchestration_demo import WINDOWS_HEALTH_SCRIPT
from apps.workflow_orchestration.services.conductor import ConductorUnavailable
from apps.workflow_orchestration.services.live_acceptance import run_live_acceptance


class Command(BaseCommand):
    help = "运行编排中心本地真实闭环验收（不伪造成功结果）"

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--domain", default="domain.com")
        parser.add_argument("--channel-id", type=int, default=1)
        parser.add_argument("--timeout", type=int, default=90)
        parser.add_argument("--target-ip", default="10.10.90.120")
        parser.add_argument(
            "--report-path",
            default="",
            help="可选：把 JSON 报告写到文件",
        )

    def handle(self, *args, **options):
        try:
            report = run_live_acceptance(
                team_id=int(options["team_id"]),
                username=str(options["username"]).strip(),
                domain=str(options["domain"]).strip(),
                channel_id=int(options["channel_id"]),
                timeout_seconds=int(options["timeout"]),
                target_ip=str(options["target_ip"]).strip(),
                health_script=WINDOWS_HEALTH_SCRIPT,
            )
        except (ValueError, ConductorUnavailable) as error:
            raise CommandError(str(error)) from error

        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        report_path = str(options["report_path"] or "").strip()
        if report_path:
            path = Path(report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"真实闭环报告已写入 {path}"))
        self.stdout.write(payload)
        if report["summary"]["failed"]:
            raise CommandError(f"真实闭环验收结束：passed={report['summary']['passed']} " f"failed={report['summary']['failed']}（失败未伪造）")
        self.stdout.write(self.style.SUCCESS(f"真实闭环验收全部通过：passed={report['summary']['passed']}"))
