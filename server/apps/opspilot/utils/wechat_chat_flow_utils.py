import time

import xmltodict
from django.http import HttpResponse
from wechatpy.enterprise import WeChatClient
from wechatpy.enterprise.events import EVENT_TYPES
from wechatpy.enterprise.messages import MESSAGE_TYPES
from wechatpy.messages import UnknownMessage
from wechatpy.utils import to_text

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine


class WechatChatFlowUtils(object):
    def __init__(self, bot_id):
        """初始化企业微信ChatFlow工具类

        Args:
            bot_id: Bot ID
        """
        self.bot_id = bot_id

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

    def validate_bot_and_workflow(self):
        """验证Bot和ChatFlow配置

        Returns:
            tuple: (bot_chat_flow, error_response)
                   如果验证失败，error_response不为None
        """

        # 验证Bot对象
        bot_obj = Bot.objects.filter(id=self.bot_id, online=True).first()
        if not bot_obj:
            logger.error(f"企业微信ChatFlow执行失败：Bot {self.bot_id} 不存在或未上线")
            return None, HttpResponse("success")

        # 验证工作流配置
        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
        if not bot_chat_flow:
            logger.error(f"企业微信ChatFlow执行失败：Bot {self.bot_id} 未配置工作流")
            return None, HttpResponse("success")

        if not bot_chat_flow.flow_json:
            logger.error(f"企业微信ChatFlow执行失败：Bot {self.bot_id} 工作流配置为空")
            return None, HttpResponse("success")

        return bot_chat_flow, None

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

    def execute_chatflow_with_message(self, bot_chat_flow, node_id, message, sender_id):
        """执行ChatFlow并返回结果

        Returns:
            str: ChatFlow执行结果文本
        """
        logger.info(f"企业微信执行ChatFlow流程开始，Bot {self.bot_id}, Node {node_id}, 发送者: {sender_id}, 消息: {message[:50]}...")

        # 创建ChatFlow引擎
        engine = create_chat_flow_engine(bot_chat_flow, node_id)

        # 准备输入数据
        input_data = {
            "last_message": message,
            "user_id": sender_id,
            "bot_id": self.bot_id,
            "node_id": node_id,
            "channel": "enterprise_wechat",
        }

        # 执行ChatFlow
        result = engine.execute(input_data)

        # 处理执行结果
        if isinstance(result, dict):
            reply_text = result.get("content") or result.get("data") or str(result)
        else:
            reply_text = str(result) if result else "处理完成"

        logger.info(f"企业微信ChatFlow流程执行完成，Bot {self.bot_id}，结果长度: {len(reply_text)}")

        return reply_text

    def send_reply_to_wechat(self, reply_text, sender_id, agent_id, corp_id, secret):
        """发送回复消息到企业微信

        Args:
            reply_text: 回复文本
            sender_id: 发送者ID
            agent_id: 企业微信应用ID
            corp_id: 企业ID
            secret: 应用密钥
        """
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

            if not message:
                logger.warning(f"企业微信收到空消息，Bot {self.bot_id}，发送者: {sender_id}")
                return HttpResponse("success")

            # 执行ChatFlow
            node_id = wechat_config["node_id"]
            reply_text = self.execute_chatflow_with_message(bot_chat_flow, node_id, message, sender_id)

            # 发送回复消息
            self.send_reply_to_wechat(reply_text, sender_id, wechat_config["agent_id"], wechat_config["corp_id"], wechat_config["secret"])

            return HttpResponse("success")

        except Exception as e:
            logger.error(f"企业微信ChatFlow流程执行失败，Bot {self.bot_id}，错误: {str(e)}")
            logger.exception(e)
            return HttpResponse("success")
