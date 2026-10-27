import asyncio
import json

from django.core.management import BaseCommand
from django.utils import autoreload
from nats.aio.client import Client
from nats.aio.errors import ErrNoServers, ErrTimeout

from apps.alerts.service.snmp_trap_bridge import handle_vector_message, load_bridge_config
from apps.core.logger import alert_logger as logger
from nats_client.clients import get_nc_client


def _log_shutdown_failure(stage, err):
    """关闭失败只记类型和堆栈，不把异常正文写入日志。"""
    safe_error = RuntimeError("snmp trap bridge shutdown failed")
    logger.error(
        "event=snmp_trap_bridge_shutdown_failed failed_stage=%s error_type=%s",
        stage,
        type(err).__name__,
        exc_info=(type(safe_error), safe_error, err.__traceback__),
    )


class Command(BaseCommand):
    """SNMP Trap bridge 运行入口。

    这个命令常驻订阅 NATS subject `vector`，把其中的 SNMP Trap 消息
    转换后投递到 alerts 的 source-specific webhook。

    它和日志模块解耦：
    - 不读取 apps.log 内部模型
    - 只依赖共享的 NATS 采集总线与 alerts webhook 契约
    """

    help = "Starts the SNMP trap bridge consumer."

    def __init__(self, *args, **kwargs):
        self.nats = Client()
        self.config = load_bridge_config()
        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--reload",
            action="store_true",
            dest="reload",
            help="Enable autoreload in development environment.",
        )

    def handle(self, *args, **options):
        reload = options.get("reload", False)
        self.stdout.write("** Starting SNMP trap bridge" + (" with reload enabled" if reload else ""))
        if reload:
            autoreload.run_with_reloader(self.inner_run, *args, **options)
        else:
            self.inner_run(*args, **options)

    def inner_run(self, *args, **options):
        """连接并订阅成功后才常驻；启动失败时让异常退出进程。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.bridge_coroutine())
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            # 清理失败只记日志。中断也在这里吞掉，避免盖住连接或订阅阶段的原始异常。
            try:
                loop.run_until_complete(self.nats.close())
            except Exception as err:
                _log_shutdown_failure("close_nats", err)
            except KeyboardInterrupt:
                pass
            try:
                loop.close()
            except Exception as err:
                _log_shutdown_failure("close_event_loop", err)
            except KeyboardInterrupt:
                pass

    async def bridge_coroutine(self):
        """建立 NATS 连接并持续消费目标 subject。"""
        try:
            await get_nc_client(self.nats)
            self.stdout.write(self.style.SUCCESS("** Connected to NATS server"))
        except (ErrNoServers, ErrTimeout) as err:
            logger.error("snmp trap bridge failed to connect to NATS: %s", str(err), exc_info=True)
            raise

        subject = self.config["subject"]

        async def callback(msg):
            # vector subject 上可能有非 JSON 或非 SNMP 消息，bridge 需要有选择地忽略。
            try:
                payload = json.loads(msg.data.decode())
            except json.JSONDecodeError:
                logger.warning("snmp trap bridge ignored non-json message on subject=%s", msg.subject)
                return

            try:
                processed = handle_vector_message(payload, self.config)
                if processed:
                    logger.info("snmp trap bridge processed event from subject=%s", msg.subject)
            except Exception as err:  # noqa
                logger.error(
                    "snmp trap bridge failed to process message on subject=%s: %s",
                    msg.subject,
                    str(err),
                    exc_info=True,
                )

        await self.nats.subscribe(subject, cb=callback)
        self.stdout.write(self.style.SUCCESS(f"** Listening on subject: {subject}"))
