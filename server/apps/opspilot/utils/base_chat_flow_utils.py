"""第三方渠道 ChatFlow 工具基类

提取企业微信、微信公众号、钉钉等第三方渠道的公共逻辑：
- Bot 和工作流验证
- ChatFlow 执行
- 消息去重
- 异步处理框架
"""

import threading
from abc import ABC, abstractmethod

from django.core.cache import cache
from django.http import HttpResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

# 消息去重缓存过期时间（秒）- 第三方平台重试间隔约为5秒，3次重试共约15秒
MESSAGE_DEDUP_EXPIRE_SECONDS = 60


class BaseChatFlowUtils(ABC):
    """第三方渠道 ChatFlow 工具基类"""

    # 子类需要定义的属性
    channel_name: str = ""  # 渠道名称，用于日志
    channel_code: str = ""  # 渠道代码，用于 input_data
    cache_key_prefix: str = ""  # 缓存键前缀，用于消息去重

    def __init__(self, bot_id):
        """初始化工具类

        Args:
            bot_id: Bot ID
        """
        self.bot_id = bot_id

    def validate_bot_and_workflow(self):
        """验证 Bot 和 ChatFlow 配置

        Returns:
            tuple: (bot_chat_flow, error_response)
                   如果验证失败，error_response 不为 None
        """
        # 验证 Bot 对象
        bot_obj = Bot.objects.filter(id=self.bot_id, online=True).first()
        if not bot_obj:
            logger.error(f"{self.channel_name}ChatFlow执行失败：Bot {self.bot_id} 不存在或未上线")
            return None, self._create_error_response()

        # 验证工作流配置
        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
        if not bot_chat_flow:
            logger.error(f"{self.channel_name}ChatFlow执行失败：Bot {self.bot_id} 未配置工作流")
            return None, self._create_error_response()

        if not bot_chat_flow.flow_json:
            logger.error(f"{self.channel_name}ChatFlow执行失败：Bot {self.bot_id} 工作流配置为空")
            return None, self._create_error_response()

        return bot_chat_flow, None

    @staticmethod
    def _create_error_response():
        """创建错误响应，子类可覆盖以返回不同格式"""
        return HttpResponse("success")

    def execute_chatflow_with_message(self, bot_chat_flow, node_id, message, sender_id):
        """执行 ChatFlow 并返回结果

        Args:
            bot_chat_flow: Bot 工作流对象
            node_id: 节点 ID
            message: 用户消息
            sender_id: 发送者 ID

        Returns:
            str: ChatFlow 执行结果文本
        """
        logger.info(f"{self.channel_name}执行ChatFlow流程开始，Bot {self.bot_id}, Node {node_id}")

        # 创建 ChatFlow 引擎
        engine = create_chat_flow_engine(bot_chat_flow, node_id)

        # 准备输入数据（第三方渠道固定为 True）
        input_data = {
            "last_message": message,
            "user_id": sender_id,
            "bot_id": self.bot_id,
            "node_id": node_id,
            "channel": self.channel_code,
            "is_third_party": True,
        }

        # 执行 ChatFlow
        result = engine.execute(input_data)

        # 处理执行结果
        if isinstance(result, dict):
            reply_text = result.get("content") or result.get("data") or str(result)
        else:
            reply_text = str(result) if result else "处理完成"

        logger.info(f"{self.channel_name}ChatFlow流程执行完成，Bot {self.bot_id}")

        return reply_text

    def is_message_processed(self, msg_id: str) -> bool:
        """检查消息是否已处理（去重）

        Args:
            msg_id: 消息唯一标识

        Returns:
            bool: True 表示已处理过，False 表示未处理
        """
        cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
        if cache.get(cache_key):
            return True
        # 标记为已处理
        cache.set(cache_key, "1", MESSAGE_DEDUP_EXPIRE_SECONDS)
        return False

    def process_message_async(self, process_func, *args, **kwargs):
        """异步处理消息

        Args:
            process_func: 处理函数
            *args: 处理函数的位置参数
            **kwargs: 处理函数的关键字参数
        """
        thread = threading.Thread(
            target=process_func,
            args=args,
            kwargs=kwargs,
            daemon=True,
        )
        thread.start()

    @abstractmethod
    def send_reply(self, reply_text: str, sender_id: str, config: dict):
        """发送回复消息

        子类必须实现此方法，处理各渠道特定的消息发送逻辑

        Args:
            reply_text: 回复文本
            sender_id: 发送者 ID
            config: 渠道配置
        """
        pass

    def async_process_and_reply(self, bot_chat_flow, config, message, sender_id, msg_id):
        """异步处理消息并回复（通用实现）

        Args:
            bot_chat_flow: Bot 工作流对象
            config: 渠道配置
            message: 用户消息
            sender_id: 发送者 ID
            msg_id: 消息 ID
        """
        try:
            node_id = config["node_id"]
            reply_text = self.execute_chatflow_with_message(bot_chat_flow, node_id, message, sender_id)
            self.send_reply(reply_text, sender_id, config)
        except Exception as e:
            logger.error(f"{self.channel_name}异步处理消息失败，Bot {self.bot_id}，MsgId {msg_id}，错误: {str(e)}")
            logger.exception(e)
