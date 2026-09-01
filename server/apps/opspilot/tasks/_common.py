import concurrent.futures
import os

from django.core.exceptions import SynchronousOnlyOperation
from django.db import close_old_connections

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow

MEMORY_WRITE_PROCESSING_TTL_SECONDS = int(os.getenv("MEMORY_WRITE_PROCESSING_TTL_SECONDS", "1800"))

def _run_in_native_thread(func, *args, **kwargs):
    def _execute(allow_async_unsafe=False):
        close_old_connections()
        previous_async_flag = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
        if allow_async_unsafe:
            os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()
            if allow_async_unsafe:
                if previous_async_flag is None:
                    os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
                else:
                    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = previous_async_flag

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(_execute, False)
            return future.result()
        except SynchronousOnlyOperation:
            logger.warning("Fallback with DJANGO_ALLOW_ASYNC_UNSAFE for eventlet ORM task")
            future = executor.submit(_execute, True)
            return future.result()

def _get_bot_chat_flow(bot_id):
    """获取 Bot 的 ChatFlow 配置

    Args:
        bot_id: Bot ID

    Returns:
        BotWorkFlow 对象，如果不存在则返回 None
    """
    bot = Bot.objects.filter(id=bot_id, online=True).first()
    if not bot:
        return None
    return BotWorkFlow.objects.filter(bot_id=bot.id).first()


def _run_channel_message(task, handler_cls, bot_id, msg_id, message, sender_id, config, channel_label):
    """渠道消息处理的共享执行体（async_process_and_reply 风格）

    被企业微信 / 微信公众号等任务复用，差异仅在于 handler 类与日志前缀。

    两阶段去重：调用前已标记为 processing，成功后由 async_process_and_reply 内部
    标记 completed，失败时其内部已调用 mark_message_failed，这里仅负责触发 Celery 重试。

    Args:
        task: 绑定的 Celery 任务实例（用于 task.retry）
        handler_cls: ChatFlow 处理器类
        bot_id: Bot ID
        msg_id: 消息唯一标识
        message: 用户消息内容
        sender_id: 发送者 ID
        config: 渠道配置（包含 node_id 等）
        channel_label: 日志中使用的渠道名称
    """

    def _execute():
        handler = handler_cls(bot_id)
        try:
            bot_chat_flow = _get_bot_chat_flow(bot_id)
            if not bot_chat_flow:
                logger.error(f"{channel_label}消息处理失败：Bot {bot_id} 不存在或未配置 ChatFlow")
                handler.mark_message_failed(msg_id)
                return

            # 执行 ChatFlow 并发送回复
            handler.async_process_and_reply(bot_chat_flow, config, message, sender_id, msg_id)
            logger.info(f"{channel_label}消息处理成功: bot_id={bot_id}, msg_id={msg_id}")

        except Exception as e:
            logger.exception(f"{channel_label}消息处理失败: bot_id={bot_id}, msg_id={msg_id}, error={str(e)}")
            # async_process_and_reply 内部已调用 mark_message_failed
            # 触发 Celery 重试
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        # Celery 重试
        raise task.retry(exc=e)
