from django.core.management.base import BaseCommand, CommandError

from apps.log.services.log_extractor.auth import rotate_system_vector_token
from apps.log.services.log_extractor.publication import ensure_initial_snapshot


class Command(BaseCommand):
    help = "确保中心 Vector 初始快照并生成或轮换部署级 Token"

    def handle(self, *args, **options):
        try:
            ensure_initial_snapshot()
            token = rotate_system_vector_token()
        except Exception as exc:
            raise CommandError(f"中心 Vector Token 轮换失败（{type(exc).__name__}）") from exc
        self.stdout.write(f"token={token}")
        self.stdout.write("请立即保存 Token、更新默认部署 Secret 并重启中心 Vector；再次执行会使本 Token 失效。")
