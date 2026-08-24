from django.core.management.base import BaseCommand, CommandError

from apps.log.services.log_extractor.publication import republish_current_config


class Command(BaseCommand):
    help = "同步重新编译并发布当前完整的系统 Vector 配置快照"

    def handle(self, *args, **options):
        try:
            snapshot = republish_current_config()
        except Exception as exc:
            raise CommandError(f"系统 Vector 配置重新发布失败（{type(exc).__name__}）") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"published generation={snapshot.generation} "
                f"contract_version={snapshot.contract_version} checksum={snapshot.checksum}"
            )
        )
