"""第三方渠道 ChatFlow 工具基类

提取企业微信、微信公众号、钉钉等第三方渠道的公共逻辑：
- Bot 和工作流验证
- ChatFlow 执行
- 消息去重（两阶段：processing → completed）
- Celery 任务处理

配置项（常量，如需修改请直接编辑本文件）：
    MESSAGE_PROCESSING_EXPIRE_SECONDS:
        消息"处理中"状态的缓存过期时间（秒），默认 300（5 分钟）。
        超时后允许重试（Celery 重试或平台重发）。
        如果 ChatFlow 执行时间较长，可适当增大此值。

    MESSAGE_COMPLETED_EXPIRE_SECONDS:
        消息"已完成"状态的缓存过期时间（秒），默认 86400（24 小时）。
        防止同一消息在此时间内被重复处理。
        对于高频消息场景，可适当减小此值以节省缓存空间。

两阶段去重流程：
    1. 收到消息 → 检查缓存状态
    2. 状态为 None → 标记为 "processing"（短 TTL）→ 开始处理
    3. 处理成功 → 标记为 "completed"（长 TTL）
    4. 处理失败 → 清除标记（允许重试）
    5. 状态为 "processing" 或 "completed" → 跳过处理
"""

from abc import ABC, abstractmethod

from django.core.cache import cache
from django.http import HttpResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

# 两阶段去重缓存过期时间
MESSAGE_PROCESSING_EXPIRE_SECONDS = 300  # 处理中状态 5 分钟超时（允许超时后重试）
MESSAGE_COMPLETED_EXPIRE_SECONDS = 86400  # 已完成状态 24 小时（防止重复处理）


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
            if result.get("success") is False:
                # 工作流失败：返回可读的失败消息，而非把内部错误结构(dict)整体 str() 发给用户
                reply_text = result.get("last_message") or result.get("error") or "处理失败，请稍后重试"
            else:
                reply_text = result.get("content") or result.get("data") or result.get("last_message") or str(result)
        else:
            reply_text = str(result) if result else "处理完成"

        logger.info(f"{self.channel_name}ChatFlow流程执行完成，Bot {self.bot_id}")

        return reply_text

    def is_message_processed(self, msg_id: str) -> bool:
        """检查消息是否已处理（两阶段去重，原子操作）

        状态转换：
        - None → processing (5min TTL) → completed (24h TTL)
        - 失败时清除 → None（允许 Celery 重试或平台重试）

        并发安全：
        - 使用 cache.add() 原子操作获取处理权
        - 多个 worker 同时到达时，只有一个能成功获取

        Args:
            msg_id: 消息唯一标识

        Returns:
            bool: True 表示已处理或处理中，False 表示可以处理
        """
        cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
        status = cache.get(cache_key)

        if status == "completed":
            logger.debug(f"{self.channel_name}消息已完成处理，跳过: msg_id={msg_id}")
            return True
        if status == "processing":
            logger.debug(f"{self.channel_name}消息处理中，跳过: msg_id={msg_id}")
            return True

        # 原子操作：尝试获取处理权
        # cache.add() 只在 key 不存在时设置，返回 True 表示设置成功
        # 这避免了 get() + set() 之间的竞态条件
        acquired = cache.add(cache_key, "processing", MESSAGE_PROCESSING_EXPIRE_SECONDS)
        if acquired:
            logger.debug(f"{self.channel_name}获取消息处理权: msg_id={msg_id}")
            return False  # 成功获取处理权，可以处理
        else:
            # 其他 worker 已获取处理权（在 get() 和 add() 之间的窗口）
            logger.debug(f"{self.channel_name}消息处理权已被其他进程获取，跳过: msg_id={msg_id}")
            return True

    def mark_message_completed(self, msg_id: str):
        """标记消息处理完成

        Args:
            msg_id: 消息唯一标识
        """
        cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
        cache.set(cache_key, "completed", MESSAGE_COMPLETED_EXPIRE_SECONDS)
        logger.debug(f"{self.channel_name}消息处理完成: msg_id={msg_id}")

    def mark_message_failed(self, msg_id: str):
        """标记消息处理失败，清除去重标记允许重试

        Args:
            msg_id: 消息唯一标识
        """
        cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
        cache.delete(cache_key)
        logger.info(f"{self.channel_name}消息处理失败，已清除去重标记: msg_id={msg_id}")

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
        """处理消息并回复（供 Celery 任务调用）

        注意：此方法现在由 Celery 任务调用，不再由 daemon 线程调用。
        成功时标记 completed，失败时标记 failed 允许重试。

        Args:
            bot_chat_flow: Bot 工作流对象
            config: 渠道配置
            message: 用户消息
            sender_id: 发送者 ID
            msg_id: 消息 ID

        Raises:
            Exception: 处理失败时抛出异常，供 Celery 重试
        """
        try:
            node_id = config["node_id"]
            reply_text = self.execute_chatflow_with_message(bot_chat_flow, node_id, message, sender_id)
            self.send_reply(reply_text, sender_id, config)
            # 成功：标记为已完成
            self.mark_message_completed(msg_id)
        except Exception as e:
            logger.error(f"{self.channel_name}消息处理失败，Bot {self.bot_id}，MsgId {msg_id}，错误: {str(e)}")
            # 失败：清除去重标记，允许重试
            self.mark_message_failed(msg_id)
            raise
