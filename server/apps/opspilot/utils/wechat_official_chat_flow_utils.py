import base64
import time

import xmltodict
from django.http import HttpResponse
from wechatpy import WeChatClient, parse_message
from wechatpy.crypto import PrpCrypto
from wechatpy.events import EVENT_TYPES
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.messages import MESSAGE_TYPES, UnknownMessage
from wechatpy.utils import check_signature, to_binary, to_text

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine


class WechatOfficialChatFlowUtils(object):
    def __init__(self, bot_id):
        """初始化微信公众号ChatFlow工具类

        Args:
            bot_id: Bot ID
        """
        self.bot_id = bot_id

    def send_message_chunks(self, openid, text: str, appid, secret):
        """分片发送较长的消息

        Args:
            openid: 用户OpenID
            text: 消息文本
            appid: 公众号AppID
            secret: 公众号Secret
        """
        if not text:
            return

        wechat_client = WeChatClient(appid, secret)

        # 公众号客服消息单次最大长度2048字符
        max_length = 1800

        if len(text) <= max_length:
            wechat_client.message.send_text(openid, text)
            logger.info(f"微信公众号发送单条消息成功，Bot {self.bot_id}")
            return

        # 按最大长度切分消息
        chunk_count = (len(text) + max_length - 1) // max_length
        logger.info(f"微信公众号消息过长，需分{chunk_count}片发送，Bot {self.bot_id}")

        start = 0
        chunk_index = 1
        while start < len(text):
            end = start + max_length
            chunk = text[start:end]
            time.sleep(0.2)  # 避免发送过快
            wechat_client.message.send_text(openid, chunk)
            logger.info(f"微信公众号发送第{chunk_index}/{chunk_count}片消息成功，Bot {self.bot_id}")
            start = end
            chunk_index += 1

    @staticmethod
    def parse_message(xml):
        """解析微信公众号消息

        Args:
            xml: XML格式的消息

        Returns:
            解析后的消息对象
        """
        if not xml:
            return None

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
            logger.error(f"微信公众号ChatFlow执行失败：Bot {self.bot_id} 不存在或未上线")
            return None, HttpResponse("success")

        # 验证工作流配置
        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
        if not bot_chat_flow:
            logger.error(f"微信公众号ChatFlow执行失败：Bot {self.bot_id} 未配置工作流")
            return None, HttpResponse("success")

        if not bot_chat_flow.flow_json:
            logger.error(f"微信公众号ChatFlow执行失败：Bot {self.bot_id} 工作流配置为空")
            return None, HttpResponse("success")

        return bot_chat_flow, None

    def get_wechat_official_node_config(self, bot_chat_flow):
        """从ChatFlow中获取微信公众号节点配置

        Returns:
            tuple: (wechat_config_dict, error_response)
                   成功时返回配置字典和None，失败时返回None和错误响应
        """
        flow_nodes = bot_chat_flow.flow_json.get("nodes", [])
        wechat_nodes = [node for node in flow_nodes if node.get("type") == "wechat_official"]

        if not wechat_nodes:
            logger.error(f"微信公众号ChatFlow执行失败：Bot {self.bot_id} 工作流中没有微信公众号节点")
            return None, HttpResponse("success")

        wechat_node = wechat_nodes[0]
        wechat_data = wechat_node.get("data", {})
        wechat_config = wechat_data.get("config", {})

        # 验证必需参数（安全模式需要 token, appid, secret, aes_key）
        required_params = ["token", "appid", "secret", "aes_key"]
        missing_params = [p for p in required_params if not wechat_config.get(p)]
        wechat_config["node_id"] = wechat_node["id"]

        if missing_params:
            logger.error(f"微信公众号ChatFlow执行失败：Bot {self.bot_id} 缺少配置参数: {', '.join(missing_params)}")
            return None, HttpResponse("success")

        return wechat_config, None

    def handle_url_verification(self, signature, timestamp, nonce, echostr, token, aes_key, appid):
        """处理微信公众号URL验证（GET请求）

        Args:
            signature: 微信加密签名
            timestamp: 时间戳
            nonce: 随机数
            echostr: 加密的随机字符串
            token: 公众号Token
            aes_key: 消息加密密钥
            appid: 公众号AppID

        Returns:
            HttpResponse: URL验证响应
        """
        logger.info(f"微信公众号URL验证开始，Bot {self.bot_id}")

        if not echostr:
            logger.error(f"微信公众号URL验证失败：缺少echostr参数，Bot {self.bot_id}")
            return HttpResponse("fail")

        try:
            check_signature(token, signature, timestamp, nonce)
            return HttpResponse(echostr)
        except InvalidSignatureException:
            logger.error(f"微信公众号URL验证失败：签名验证失败，Bot {self.bot_id}")
            return HttpResponse("fail")
        except Exception as e:
            logger.error(f"微信公众号URL验证失败，Bot {self.bot_id}，错误: {str(e)}")
            logger.exception(e)
            return HttpResponse("fail")

    def execute_chatflow_with_message(self, bot_chat_flow, node_id, message, sender_id):
        """执行ChatFlow并返回结果

        Args:
            bot_chat_flow: Bot工作流对象
            node_id: 节点ID
            message: 用户消息
            sender_id: 发送者ID（OpenID）

        Returns:
            str: ChatFlow执行结果文本
        """
        logger.info(f"微信公众号执行ChatFlow流程开始，Bot {self.bot_id}, Node {node_id}")

        # 创建ChatFlow引擎
        engine = create_chat_flow_engine(bot_chat_flow, node_id)

        # 准备输入数据
        input_data = {
            "last_message": message,
            "user_id": sender_id,
            "bot_id": self.bot_id,
            "node_id": node_id,
            "channel": "wechat_official_account",
        }

        # 执行ChatFlow
        result = engine.execute(input_data)

        # 处理执行结果
        if isinstance(result, dict):
            reply_text = result.get("content") or result.get("data") or str(result)
        else:
            reply_text = str(result) if result else "处理完成"

        logger.info(f"微信公众号ChatFlow流程执行完成，Bot {self.bot_id}")

        return reply_text

    def send_reply_to_wechat(self, reply_text, openid, appid, secret):
        """发送回复消息到微信公众号（使用客服消息接口）

        Args:
            reply_text: 回复文本
            openid: 用户OpenID
            appid: 公众号AppID
            secret: 公众号Secret
        """
        if not reply_text:
            logger.warning(f"微信公众号回复消息为空，Bot {self.bot_id}")
            return

        # 处理换行符
        reply_text = reply_text.replace("\r\n", "\n").replace("\r", "\n")

        try:
            # 使用客服消息接口发送
            self.send_message_chunks(openid, reply_text, appid, secret)
            logger.info(f"微信公众号消息发送成功，Bot {self.bot_id}")
        except Exception as e:
            logger.error(f"微信公众号发送消息失败，Bot {self.bot_id}，错误: {str(e)}")
            logger.exception(e)

    def decrypt(self, encrypt, aes_key, appid):
        encoding_aes_key = to_binary(aes_key + "=")
        key = base64.b64decode(encoding_aes_key)
        pc = PrpCrypto(key)
        return pc.decrypt(encrypt, appid)

    def handle_wechat_message(self, request, wechat_config, bot_chat_flow):
        """处理微信公众号消息（POST请求，安全模式）

        Args:
            request: Django request对象
            wechat_config: 微信公众号配置
            bot_chat_flow: Bot工作流对象

        Returns:
            HttpResponse: 消息处理响应
        """
        signature = request.GET.get("signature", "") or request.GET.get("msg_signature", "")
        timestamp = request.GET.get("timestamp", "")
        nonce = request.GET.get("nonce", "")

        logger.info(f"微信公众号收到POST请求，Bot {self.bot_id}")

        # 验证参数完整性
        if not signature or not timestamp or not nonce:
            logger.error(f"微信公众号消息处理失败：缺少签名参数，Bot {self.bot_id}")
            return HttpResponse("success")

        try:
            xml_msg = xmltodict.parse(to_text(request.body))["xml"]
            decode_msg = self.decrypt(xml_msg["Encrypt"], wechat_config["aes_key"], wechat_config["appid"])
            msg = parse_message(decode_msg)

            if not msg:
                logger.warning(f"微信公众号消息解析失败，Bot {self.bot_id}")
                return HttpResponse("success")

            logger.info(f"微信公众号消息解析成功，Bot {self.bot_id}，消息类型: {msg.type}")

            # 只处理文本消息
            if msg.type != "text":
                logger.info(f"微信公众号收到非文本消息，类型: {msg.type}，Bot {self.bot_id}，忽略处理")
                return HttpResponse("success")

            # 获取消息内容和发送者OpenID
            message = getattr(msg, "content", "")
            openid = getattr(msg, "source", "")

            if not message:
                logger.warning(f"微信公众号收到空消息，Bot {self.bot_id}")
                return HttpResponse("success")

            logger.info(f"微信公众号收到文本消息，Bot {self.bot_id}")

            # 执行ChatFlow
            node_id = wechat_config["node_id"]
            logger.info(f"微信公众号开始执行ChatFlow，Bot {self.bot_id}")
            reply_text = self.execute_chatflow_with_message(bot_chat_flow, node_id, message, openid)

            # 发送回复消息（使用客服消息接口，异步发送）
            self.send_reply_to_wechat(reply_text, openid, wechat_config["appid"], wechat_config["secret"])

            # 微信公众号要求5秒内必须回复，这里直接返回success
            # 实际回复通过客服消息接口异步发送
            logger.info(f"微信公众号消息处理完成，Bot {self.bot_id}")
            return HttpResponse("success")

        except InvalidSignatureException:
            logger.error(f"微信公众号消息签名验证失败，Bot {self.bot_id}")
            return HttpResponse("success")
        except Exception as e:
            logger.error(f"微信公众号ChatFlow流程执行失败，Bot {self.bot_id}，错误: {str(e)}")
            logger.exception(e)
            return HttpResponse("success")
