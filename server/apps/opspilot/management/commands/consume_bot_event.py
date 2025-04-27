import datetime
import json
import time

import pika
from django.conf import settings
from django.core.management import BaseCommand
from django.db import close_old_connections

from apps.core.logger import logger
from apps.opspilot.bot_mgmt.utils import get_user_info
from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models import Bot, BotConversationHistory, ChannelUser

channel_map = {}


def on_message(channel, method_frame, header_frame, body):
    try:
        message = json.loads(body.decode())
        logger.info(f"开始处理消息: {message}")
        text = message.get("text", "") or ""
        if text.strip():
            close_old_connections()
            sender_id = message["sender_id"]
            if not sender_id.strip():
                channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                return
            bot_id = int(message.get("bot_id", 7))
            created_at = datetime.datetime.fromtimestamp(message["timestamp"], tz=datetime.timezone.utc)
            if "input_channel" in message:
                input_channel = message["input_channel"]
                channel_map[sender_id] = input_channel
            else:
                input_channel = channel_map.get(sender_id)
                if not input_channel:
                    channel_user = ChannelUser.objects.get(user_id=sender_id)
                    input_channel = (
                        channel_user.channel_type if channel_user.channel_type != ChannelChoices.WEB else "socketio"
                    )
            user, _ = get_user_info(bot_id, input_channel, sender_id)
            bot = Bot.objects.get(id=bot_id)
            msg = message.get("metadata", {}).get("other_data", {}).get("citing_knowledge", [])
            msg_str = json.dumps(msg).replace("\u0000", " ").replace(r"\u0000", " ")
            try:
                BotConversationHistory.objects.get_or_create(
                    bot_id=bot_id,
                    channel_user_id=user.id,
                    created_at=created_at,
                    created_by=bot.created_by,
                    conversation_role=message["event"],
                    conversation=message["text"] or "",
                    citing_knowledge=json.loads(msg_str),
                )
            except Exception as e:
                logger.exception(f"对话保存失败，对话内容： {msg_str}, error: {e}")
    except Exception as e:
        logger.exception(f"对话历史保存失败: {e}")
    else:
        logger.info("消息处理完成")
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)


class Command(BaseCommand):
    help = "获取对话历史"

    @staticmethod
    def create_connection():
        """创建RabbitMQ连接"""
        return pika.BlockingConnection(
            pika.ConnectionParameters(
                host=settings.CONVERSATION_MQ_HOST,
                port=settings.CONVERSATION_MQ_PORT,
                credentials=pika.PlainCredentials(settings.CONVERSATION_MQ_USER, settings.CONVERSATION_MQ_PASSWORD),
                heartbeat=600,  # 添加心跳检测，默认600秒
                blocked_connection_timeout=300,  # 添加阻塞连接超时
                connection_attempts=3,  # 连接重试次数
                retry_delay=5,  # 重试延迟时间
            )
        )

    def handle(self, *args, **options):
        while True:
            connection = None
            try:
                logger.info(f"初始化消息队列连接:[{settings.CONVERSATION_MQ_HOST}:{settings.CONVERSATION_MQ_PORT}]")
                connection = self.create_connection()
                channel = connection.channel()

                # 声明队列，确保队列存在
                channel.queue_declare(queue="pilot", durable=True)

                # 设置QoS，限制未确认消息数量
                channel.basic_qos(prefetch_count=1)

                # 设置消费者
                channel.basic_consume(queue="pilot", on_message_callback=on_message)

                logger.info("开始消费消息...")
                channel.start_consuming()
            except Exception as e:
                logger.exception(f"未预期的错误: {e}")
                time.sleep(5)
            finally:
                try:
                    if connection and not connection.is_closed:
                        connection.close()
                except Exception as e:
                    logger.error(f"关闭连接时发生错误: {e}")
                time.sleep(5)  # 重试前等待
