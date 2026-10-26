"""飞书长连接常驻进程。启动完成后由进程守护拉起，不参与启动门禁。"""

from __future__ import annotations

import time
import uuid

from django.core.management.base import BaseCommand

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.skill_channel_aibot_long_connection import redis_client_from_env
from apps.opspilot.services.skill_channel_aibot_long_connection_agent import run_long_connection_answer
from apps.opspilot.services.skill_channel_feishu_long_connection import FeishuLongConnectionLeader, load_long_connection_channels, new_leader_lock
from apps.opspilot.services.skill_channel_feishu_long_connection_sdk import open_feishu_sdk_transport

POLL_SECONDS = 1


class Command(BaseCommand):
    help = "维持已启用的飞书长连接，接收文本并更新同一条回复"

    def handle(self, *args, **options):
        redis = redis_client_from_env()
        if redis is None:
            logger.warning("event=feishu_long_connection_lock_unavailable failed_stage=lock error_type=RedisUnavailable")
        leader = FeishuLongConnectionLeader(
            lock=new_leader_lock(redis, token=uuid.uuid4().hex),
            opener=open_feishu_sdk_transport,
            agent_runner=run_long_connection_answer,
        )
        logger.info("event=feishu_long_connection_process_started")
        while True:
            try:
                leader.reconcile(load_long_connection_channels())
                leader.pump()
            except Exception as exc:
                proxy = RuntimeError(type(exc).__name__)
                proxy.__traceback__ = exc.__traceback__
                logger.error(
                    "event=feishu_long_connection_loop_failed failed_stage=reconcile error_type=%s",
                    type(exc).__name__,
                    exc_info=(type(proxy), proxy, proxy.__traceback__),
                )
            time.sleep(POLL_SECONDS)
