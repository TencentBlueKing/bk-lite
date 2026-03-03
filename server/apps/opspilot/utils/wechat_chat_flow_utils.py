"""企业微信 ChatFlow 工具类

继承 BaseChatFlowUtils，实现企业微信特定的消息发送逻辑
"""

import time

import xmltodict
from django.http import HttpResponse
from wechatpy.enterprise import WeChatClient
from wechatpy.enterprise.events import EVENT_TYPES
from wechatpy.enterprise.messages import MESSAGE_TYPES
from wechatpy.messages import UnknownMessage
from wechatpy.utils import to_text

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.base_chat_flow_utils import BaseChatFlowUtils


class WechatChatFlowUtils(BaseChatFlowUtils):
    """企业微信 ChatFlow 工具类"""

    # 渠道配置
    channel_name = "企业微信"
    channel_code = "enterprise_wechat"
    cache_key_prefix = "wechat_msg"

    def send_message_chunks(self, user_id, text: str, agent_id, corp_id, secret):
        """分片发送较长的消息"""
        if not text:
            return
        wechat_client = WeChatClient(
            corp_id,
            secret,
        )
        if len(text) <= 500:
            wechat_client.message.send_markdown(agent_id, user_id, text)
            return

        # 按最大长度切分消息
        start = 0
        while start < len(text):
            end = start + 500
            chunk = text[start:end]
            time.sleep(0.2)
            wechat_client.message.send_markdown(agent_id, user_id, chunk)
            start = end

    @staticmethod
    def parse_message(xml):
        """解析企业微信消息"""
        if not xml:
            return
        message = xmltodict.parse(to_text(xml))["xml"]
        message_type = message["MsgType"].lower()
        if message_type == "event":
            event_type = message["Event"].lower()
            message_class = EVENT_TYPES.get(event_type, UnknownMessage)
        else:
            message_class = MESSAGE_TYPES.get(message_type, UnknownMessage)
        return message_class(message)

    def get_wechat_node_config(self, bot_chat_flow):
        """从ChatFlow中获取企业微信节点配置

        Returns:
            tuple: (wechat_config_dict, error_response)
                   成功时返回配置字典和None，失败时返回None和错误响应
        """
        flow_nodes = bot_chat_flow.flow_json.get("nodes", [])
        wechat_nodes = [node for node in flow_nodes if node.get("type") == "enterprise_wechat"]

        if not wechat_nodes:
            logger.error(f"企业微信ChatFlow执行失败：Bot {self.bot_id} 工作流中没有企业微信节点")
            return None, HttpResponse("success")

        wechat_node = wechat_nodes[0]
        wechat_data = wechat_node.get("data", {})
        wechat_config = wechat_data.get("config", {})

        # 验证必需参数
        required_params = ["token", "aes_key", "corp_id", "agent_id", "secret"]
        missing_params = [p for p in required_params if not wechat_config.get(p)]
        wechat_config["node_id"] = wechat_node["id"]
        if missing_params:
            logger.error(f"企业微信ChatFlow执行失败：Bot {self.bot_id} 缺少配置参数: {', '.join(missing_params)}")
            return None, HttpResponse("success")

        return wechat_config, None

    def handle_url_verification(self, crypto, signature, timestamp, nonce, echostr):
        """处理企业微信URL验证

        Returns:
            HttpResponse: URL验证响应
        """
        if not echostr:
            logger.error("企业微信URL验证失败：缺少echostr参数")
            return HttpResponse("fail")

        try:
            logger.info(f"各参数如下： signature【{signature}】, timestamp【{timestamp}】, nonce【{nonce}】, echostr【{echostr}】")
            echo_str = crypto.check_signature(signature, timestamp, nonce, echostr)
            logger.info(f"企业微信URL验证成功，Bot {self.bot_id}")
            return HttpResponse(echo_str)
        except Exception as e:
            logger.error(f"企业微信URL验证失败，Bot {self.bot_id}，错误: {str(e)}")
            return HttpResponse("fail")

    def send_reply(self, reply_text: str, sender_id: str, config: dict):
        """发送回复消息到企业微信（实现基类抽象方法）

        Args:
            reply_text: 回复文本
            sender_id: 发送者ID
            config: 企业微信配置，包含 agent_id, corp_id, secret
        """
        agent_id = config["agent_id"]
        corp_id = config["corp_id"]
        secret = config["secret"]

        # 处理换行符
        reply_text = reply_text.replace("\r\n", "\n").replace("\r", "\n")
        reply_text_list = reply_text.split("\n")

        # 每50行发送一次，避免消息过长
        for i in range(0, len(reply_text_list), 50):
            msg_chunk = "\n".join(reply_text_list[i : i + 50])
            if msg_chunk.strip():  # 只发送非空消息
                try:
                    self.send_message_chunks(sender_id, msg_chunk, agent_id, corp_id, secret)
                except Exception as send_err:
                    logger.error(f"企业微信发送消息失败，Bot {self.bot_id}，错误: {str(send_err)}")

    def handle_wechat_message(self, request, crypto, bot_chat_flow, wechat_config):
        """处理企业微信消息

        采用异步处理模式：
        1. 立即返回success给企业微信（避免5秒超时重试）
        2. 使用消息ID去重（防止重试导致重复处理）
        3. 异步执行ChatFlow并通过主动发送接口回复

        Returns:
            HttpResponse: 消息处理响应
        """
        signature = request.GET.get("signature", "") or request.GET.get("msg_signature", "")
        timestamp = request.GET.get("timestamp", "")
        nonce = request.GET.get("nonce", "")

        # 验证参数完整性
        if not signature or not timestamp or not nonce:
            logger.error(f"企业微信消息处理失败：缺少签名参数，Bot {self.bot_id}")
            return HttpResponse("success")

        try:
            # 解密消息
            decrypted_xml = crypto.decrypt_message(request.body, signature, timestamp, nonce)

            # 解析消息
            msg = self.parse_message(decrypted_xml)

            # 只处理文本消息
            if msg.type != "text":
                logger.info(f"企业微信收到非文本消息，类型: {msg.type}，Bot {self.bot_id}，忽略处理")
                return HttpResponse("success")

            # 获取消息内容和发送者
            message = getattr(msg, "content", "")
            sender_id = getattr(msg, "source", "")
            msg_id = getattr(msg, "id", "") or f"{sender_id}:{hash(message)}:{timestamp}"

            if not message:
                logger.warning(f"企业微信收到空消息，Bot {self.bot_id}，发送者: {sender_id}")
                return HttpResponse("success")

            # 消息去重检查（使用基类方法）
            if self.is_message_processed(msg_id):
                logger.info(f"企业微信消息已处理，跳过重复消息，Bot {self.bot_id}，MsgId {msg_id}")
                return HttpResponse("success")

            # 异步处理消息（使用基类方法，立即返回避免超时）
            self.process_message_async(
                self.async_process_and_reply,
                bot_chat_flow,
                wechat_config,
                message,
                sender_id,
                msg_id,
            )

            logger.info(f"企业微信消息已接收，异步处理中，Bot {self.bot_id}，MsgId {msg_id}")
            return HttpResponse("success")

        except Exception as e:
            logger.error(f"企业微信ChatFlow流程执行失败，Bot {self.bot_id}，错误: {str(e)}")
            logger.exception(e)
            return HttpResponse("success")
