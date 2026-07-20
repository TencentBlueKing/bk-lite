"""声明监控指标的 JetStream 流。"""

import os

from django.core.management.base import BaseCommand, CommandError

from nats_client.clients import ensure_stream_sync


MONITOR_METRICS_STREAM_NAME = "BK_MONITOR_METRICS"
MONITOR_METRICS_SUBJECTS = ["metrics.*"]
# 采集端短暂不可用时仍可回放；上限同时受 NATS 服务端总文件存储限制约束。
MONITOR_METRICS_MAX_AGE_SECONDS = 3 * 24 * 60 * 60
MONITOR_METRICS_MAX_BYTES = 1024 * 1024 * 1024


def _positive_int_from_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = int(value)
    except ValueError as error:
        raise CommandError(f"{name} 必须是正整数，当前值: {value!r}") from error
    if parsed <= 0:
        raise CommandError(f"{name} 必须是正整数，当前值: {value!r}")
    return parsed


class Command(BaseCommand):
    help = "幂等创建或更新监控指标 JetStream 流"

    def handle(self, *args, **options):
        max_age = _positive_int_from_env(
            "MONITOR_METRICS_STREAM_MAX_AGE_SECONDS", MONITOR_METRICS_MAX_AGE_SECONDS
        )
        max_bytes = _positive_int_from_env(
            "MONITOR_METRICS_STREAM_MAX_BYTES", MONITOR_METRICS_MAX_BYTES
        )
        try:
            ensure_stream_sync(
                MONITOR_METRICS_STREAM_NAME,
                MONITOR_METRICS_SUBJECTS,
                max_age,
                max_bytes,
            )
        except Exception as error:
            raise CommandError(
                "无法声明监控指标 JetStream 流；请确认 NATS 已启用 JetStream，"
                "并检查 NATS 连通性与 MONITOR_METRICS_STREAM_MAX_BYTES 容量配置。"
            ) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"监控指标 JetStream 流已就绪: {MONITOR_METRICS_STREAM_NAME} ({', '.join(MONITOR_METRICS_SUBJECTS)})"
            )
        )
