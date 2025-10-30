import hashlib
import hmac
import json
import threading
from base64 import b64encode

import dingtalk_stream
import requests
from django.http import JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine


class DingTalkChatFlowUtils(object):
    def __init__(self, bot_id):
        """初始化钉钉ChatFlow工具类

        Args:
            bot_id: Bot ID
        """
        self.bot_id = bot_id

    def validate_bot_and_workflow(self):
        """验证Bot和ChatFlow配置

        Returns:
            tuple: (bot_chat_flow, error_response)
                   如果验证失败，error_response不为None
        """
        # 验证Bot对象
        bot_obj = Bot.objects.filter(id=self.bot_id, online=True).first()
        if not bot_obj:
            logger.error(f"钉钉ChatFlow执行失败：Bot {self.bot_id} 不存在或未上线")
            return None, JsonResponse({"success": False, "message": "Bot not found"})

        # 验证工作流配置
        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
        if not bot_chat_flow:
            logger.error(f"钉钉ChatFlow执行失败：Bot {self.bot_id} 未配置工作流")
            return None, JsonResponse({"success": False, "message": "Workflow not configured"})

        if not bot_chat_flow.flow_json:
            logger.error(f"钉钉ChatFlow执行失败：Bot {self.bot_id} 工作流配置为空")
            return None, JsonResponse({"success": False, "message": "Workflow config is empty"})

        return bot_chat_flow, None

    def get_dingtalk_node_config(self, bot_chat_flow):
        """从ChatFlow中获取钉钉节点配置

        Returns:
            tuple: (dingtalk_config_dict, error_response)
                   成功时返回配置字典和None，失败时返回None和错误响应
        """
        flow_nodes = bot_chat_flow.flow_json.get("nodes", [])
        dingtalk_nodes = [node for node in flow_nodes if node.get("type") == "dingtalk"]

        if not dingtalk_nodes:
            logger.error(f"钉钉ChatFlow执行失败：Bot {self.bot_id} 工作流中没有钉钉节点")
            return None, JsonResponse({"success": False, "message": "DingTalk node not found"})

        dingtalk_node = dingtalk_nodes[0]
        dingtalk_data = dingtalk_node.get("data", {})
        dingtalk_config = dingtalk_data.get("config", {})

        # 验证必需参数
        required_params = ["client_id", "client_secret"]
        missing_params = [p for p in required_params if not dingtalk_config.get(p)]
        dingtalk_config["node_id"] = dingtalk_node["id"]
        if missing_params:
            logger.error(f"钉钉ChatFlow执行失败：Bot {self.bot_id} 缺少配置参数: {', '.join(missing_params)}")
            return None, JsonResponse({"success": False, "message": f"Missing config: {', '.join(missing_params)}"})

        return dingtalk_config, None

    def verify_signature(self, timestamp, sign, app_secret):
        """验证钉钉签名

        Args:
            timestamp: 时间戳
            sign: 签名
            app_secret: 应用密钥

        Returns:
            bool: 签名是否有效
        """
        try:
            # 根据钉钉文档，签名算法：HmacSHA256(timestamp + "\n" + app_secret)
            string_to_sign = f"{timestamp}\n{app_secret}"
            hmac_code = hmac.new(app_secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
            calculated_sign = b64encode(hmac_code).decode("utf-8")
            return calculated_sign == sign
        except Exception as e:
            logger.error(f"钉钉签名验证失败，Bot {self.bot_id}，错误: {str(e)}")
            return False

    def execute_chatflow_with_message(self, bot_chat_flow, node_id, message, sender_id):
        """执行ChatFlow并返回结果

        Returns:
            str: ChatFlow执行结果文本
        """
        logger.info(f"钉钉执行ChatFlow流程开始，Bot {self.bot_id}, Node {node_id}")

        # 创建ChatFlow引擎
        engine = create_chat_flow_engine(bot_chat_flow, node_id)

        # 准备输入数据
        input_data = {
            "last_message": message,
            "user_id": sender_id,
            "bot_id": self.bot_id,
            "node_id": node_id,
            "channel": "ding_talk",
        }

        # 执行ChatFlow
        result = engine.execute(input_data)

        # 处理执行结果
        if isinstance(result, dict):
            reply_text = result.get("content") or result.get("data") or str(result)
        else:
            reply_text = str(result) if result else "处理完成"

        logger.info(f"钉钉ChatFlow流程执行完成，Bot {self.bot_id}")

        return reply_text

    def get_access_token(self, app_key, app_secret):
        """获取钉钉access_token

        Args:
            app_key: 应用Key
            app_secret: 应用密钥

        Returns:
            str: access_token
        """
        try:
            url = "https://oapi.dingtalk.com/gettoken"
            params = {"appkey": app_key, "appsecret": app_secret}
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            if data.get("errcode") != 0:
                raise Exception(f"获取access_token失败: {data.get('errmsg')}")
            return data["access_token"]
        except Exception as e:
            logger.error(f"钉钉获取access_token失败，Bot {self.bot_id}，错误: {str(e)}")
            raise

    def send_message(self, webhook_url, msg_type, content):
        """发送钉钉消息

        Args:
            webhook_url: Webhook URL
            msg_type: 消息类型 (text, markdown等)
            content: 消息内容

        Returns:
            bool: 是否发送成功
        """
        try:
            if not webhook_url:
                logger.error(f"钉钉发送消息失败：缺少webhook_url，Bot {self.bot_id}")
                return False

            payload = {"msgtype": msg_type, msg_type: content}

            response = requests.post(webhook_url, json=payload, timeout=10)
            result = response.json()

            if result.get("errcode") != 0:
                logger.error(f"钉钉发送消息失败，Bot {self.bot_id}，错误: {result.get('errmsg')}")
                return False

            logger.info(f"钉钉消息发送成功，Bot {self.bot_id}")
            return True

        except Exception as e:
            logger.error(f"钉钉发送消息异常，Bot {self.bot_id}，错误: {str(e)}")
            return False

    def handle_dingtalk_message(self, request, bot_chat_flow, dingtalk_config):
        """处理钉钉消息

        Returns:
            JsonResponse: 消息处理响应
        """
        try:
            # 解析请求数据
            data = json.loads(request.body)
            logger.info(f"钉钉收到消息，Bot {self.bot_id}")

            # 验证签名（如果有）
            timestamp = request.headers.get("timestamp")
            sign = request.headers.get("sign")
            if timestamp and sign:
                if not self.verify_signature(timestamp, sign, dingtalk_config["client_secret"]):
                    logger.error(f"钉钉消息签名验证失败，Bot {self.bot_id}")
                    return JsonResponse({"success": False, "message": "Invalid signature"})

            # 获取消息内容
            msg_type = data.get("msgtype")
            if msg_type != "text":
                logger.info(f"钉钉收到非文本消息，类型: {msg_type}，Bot {self.bot_id}，忽略处理")
                return JsonResponse({"success": True})

            text_content = data.get("text", {}).get("content", "")
            sender_id = data.get("senderStaffId", "") or data.get("senderId", "")

            if not text_content:
                logger.warning(f"钉钉收到空消息，Bot {self.bot_id}")
                return JsonResponse({"success": True})

            # 执行ChatFlow
            node_id = dingtalk_config["node_id"]
            reply_text = self.execute_chatflow_with_message(bot_chat_flow, node_id, text_content, sender_id)

            # 发送回复消息（如果配置了webhook）
            webhook_url = data.get("sessionWebhook")
            if webhook_url and reply_text:
                # 发送Markdown格式消息
                markdown_content = {"title": "机器人回复", "text": reply_text}
                self.send_message(webhook_url, "markdown", markdown_content)

            return JsonResponse({"success": True, "data": {"reply": reply_text}})

        except Exception as e:
            logger.error(f"钉钉ChatFlow流程执行失败，Bot {self.bot_id}，错误: {str(e)}")
            logger.exception(e)
            return JsonResponse({"success": False, "message": str(e)})


class DingTalkStreamEventHandler(dingtalk_stream.EventHandler):
    """钉钉Stream模式事件处理器"""

    def __init__(self, bot_id):
        super().__init__()
        self.bot_id = bot_id

    async def process(self, event):
        """处理钉钉Stream事件"""
        logger.info(f"钉钉Stream收到事件，Bot {self.bot_id}")
        return dingtalk_stream.AckMessage.STATUS_OK, "OK"


class DingTalkStreamCallbackHandler(dingtalk_stream.CallbackHandler):
    """钉钉Stream模式回调处理器"""

    def __init__(self, bot_id, bot_chat_flow, dingtalk_config):
        super().__init__()
        self.bot_id = bot_id
        self.bot_chat_flow = bot_chat_flow
        self.dingtalk_config = dingtalk_config
        self.utils = DingTalkChatFlowUtils(bot_id)

    async def process(self, callback):
        """处理钉钉机器人消息回调

        Args:
            callback: 钉钉回调消息对象（dingtalk_stream.CallbackMessage）

        Returns:
            tuple: (status, reply_text)
        """
        try:
            # 获取消息内容
            incoming_message = callback.data
            logger.info(f"钉钉Stream收到消息，Bot {self.bot_id}")

            msg_type = incoming_message.get("msgtype")
            if msg_type != "text":
                logger.info(f"钉钉Stream收到非文本消息，类型: {msg_type}，Bot {self.bot_id}，忽略处理")
                return dingtalk_stream.AckMessage.STATUS_OK, "OK"

            text_content = incoming_message.get("text", {}).get("content", "")
            sender_id = incoming_message.get("senderStaffId", "") or incoming_message.get("senderId", "")

            if not text_content:
                logger.warning(f"钉钉Stream收到空消息，Bot {self.bot_id}")
                return dingtalk_stream.AckMessage.STATUS_OK, "OK"

            # 执行ChatFlow
            node_id = self.dingtalk_config["node_id"]
            reply_text = self.utils.execute_chatflow_with_message(self.bot_chat_flow, node_id, text_content, sender_id)

            logger.info(f"钉钉Stream处理完成，Bot {self.bot_id}")

            # 返回回复消息
            return dingtalk_stream.AckMessage.STATUS_OK, {"msgtype": "text", "text": {"content": reply_text}}

        except Exception as e:
            logger.error(f"钉钉Stream处理消息失败，Bot {self.bot_id}，错误: {str(e)}")
            logger.exception(e)
            return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, str(e)


def start_dingtalk_stream_client(bot_id, bot_chat_flow, dingtalk_config):
    """启动钉钉Stream客户端（长连接模式）

    Args:
        bot_id: Bot ID
        bot_chat_flow: Bot工作流对象
        dingtalk_config: 钉钉配置字典（需包含client_id和client_secret）

    Returns:
        bool: 是否成功启动
    """
    try:
        client_id = dingtalk_config.get("client_id")
        client_secret = dingtalk_config.get("client_secret")

        if not client_id or not client_secret:
            logger.error(f"钉钉Stream启动失败：缺少client_id或client_secret，Bot {bot_id}")
            return False

        # 创建凭证和客户端
        credential = dingtalk_stream.Credential(client_id, client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)

        # 注册事件处理器
        client.register_all_event_handler(DingTalkStreamEventHandler(bot_id))

        # 注册回调处理器
        callback_handler = DingTalkStreamCallbackHandler(bot_id, bot_chat_flow, dingtalk_config)
        client.register_callback_handler(dingtalk_stream.ChatbotMessage.TOPIC, callback_handler)

        # 在新线程中启动客户端
        def start_client():
            try:
                logger.info(f"钉钉Stream客户端启动中，Bot {bot_id}")
                client.start_forever()
            except Exception as e:
                logger.error(f"钉钉Stream客户端运行异常，Bot {bot_id}，错误: {str(e)}")
                logger.exception(e)

        thread = threading.Thread(target=start_client, daemon=True)
        thread.start()

        logger.info(f"钉钉Stream客户端已启动，Bot {bot_id}")
        return True

    except Exception as e:
        logger.error(f"钉钉Stream客户端启动失败，Bot {bot_id}，错误: {str(e)}")
        logger.exception(e)
        return False
