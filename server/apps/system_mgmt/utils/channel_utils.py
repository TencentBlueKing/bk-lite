import base64
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import encode_rfc2231

import requests
from wechatpy import WeChatClientException
from wechatpy.enterprise import WeChatClient

import nats_client
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Channel


def send_wechat(channel_obj: Channel, content, user_list):
    """发送企业微信消息"""
    channel_config = channel_obj.config
    channel_obj.decrypt_field("secret", channel_config)
    channel_obj.decrypt_field("token", channel_config)
    channel_obj.decrypt_field("aes_key", channel_config)
    receivers = user_list.values_list("")
    try:
        # 创建企业微信客户端
        client = WeChatClient(corp_id=channel_config["corp_id"], secret=channel_config["secret"])
        # 发送文本消息
        client.message.send_text(agent_id=channel_config["agent_id"], user_ids=receivers, content=content)
        return {"result": True, "message": "Successfully sent WeChat message"}
    except WeChatClientException as e:
        return {"result": False, "message": f"WeChat API error: {e.errmsg}"}
    except Exception as e:
        return {"result": False, "message": f"Error sending WeChat message: {str(e)}"}


def send_email(channel_obj: Channel, title, content, user_list, attachments=None):
    """发送邮件"""
    channel_config = channel_obj.config
    channel_obj.decrypt_field("smtp_pwd", channel_config)
    receivers = list(user_list.values_list("email", flat=True).distinct())
    return send_email_to_user(channel_config, content, receivers, title, attachments)


def send_email_to_user(channel_config, content, receivers, title, attachments=None):
    """
    发送邮件给用户
    :param channel_config: 邮件通道配置
    :param content: 邮件正文内容（HTML格式）
    :param receivers: 收件人邮箱列表
    :param title: 邮件主题
    :param attachments: 附件列表，每个附件格式为:
        - {"filename": "文件名", "content": "base64编码内容"} (用于NATS远程调用，推荐)
        - {"filename": "文件名", "data": bytes} (仅用于本地直接调用)
        注意: 通过NATS传输时，附件必须使用base64编码的content字段，因为NATS使用JSON序列化
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = channel_config["mail_sender"]
        msg["To"] = ",".join(receivers)
        msg["Subject"] = title
        msg.attach(MIMEText(content, "html", "utf-8"))

        # 处理附件
        if attachments:
            for attachment in attachments:
                filename = attachment.get("filename", "attachment")
                # 支持两种方式：base64编码的content（NATS传输）或原始bytes的data（本地调用）
                if "content" in attachment:
                    file_data = base64.b64decode(attachment["content"])
                elif "data" in attachment:
                    file_data = attachment["data"]
                else:
                    continue

                part = MIMEBase("application", "octet-stream")
                part.set_payload(file_data)
                # 使用 RFC 2231 编码处理中文文件名
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=encode_rfc2231(filename, "utf-8"),
                )
                # 对附件内容进行 base64 编码
                encoders.encode_base64(part)
                msg.attach(part)

        # 根据配置决定使用 SSL 还是普通连接
        if channel_config.get("smtp_usessl", False):
            server = smtplib.SMTP_SSL(channel_config["smtp_server"], channel_config["port"])
        else:
            server = smtplib.SMTP(channel_config["smtp_server"], channel_config["port"])

        # 如果配置使用 TLS，则启用 TLS
        if channel_config.get("smtp_usetls", False):
            server.starttls()

        server.login(channel_config["smtp_user"], channel_config["smtp_pwd"])
        server.send_message(msg)
        server.quit()

        return {"result": True, "message": "Successfully sent email"}
    except Exception as e:
        return {"result": False, "message": f"Error sending email: {str(e)}"}


def send_by_bot(channel_obj: Channel, content, receivers):
    if receivers:
        to_user_mentions = " ".join(f"@{name} " for name in receivers)
        content = f"{content}\nTo: {to_user_mentions}"
    channel_config = channel_obj.config
    payload = {"msgtype": "markdown", "markdown": {"content": content}}

    # 优先使用 bot_key（企业微信机器人），其次使用 webhook_url（通用 webhook）
    channel_obj.decrypt_field("webhook_url", channel_config)
    webhook_url = channel_config.get("webhook_url")
    if not webhook_url:
        channel_obj.decrypt_field("bot_key", channel_config)
        bot_key = channel_config.get("bot_key")
        webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={bot_key}"
    try:
        res = requests.post(webhook_url, json=payload, timeout=5)
        return res.json()
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": "failed to send bot message"}


def send_nats_message(channel_obj: Channel, content: dict):
    """
    发送 NATS 消息（Request 模式）
    :param channel_obj: NATS Channel 对象
    :param content: 消息内容，dict 类型，将作为 kwargs 传递给目标方法
    :return: 目标服务的响应
    """
    config = channel_obj.config
    namespace = config.get("namespace")
    method_name = config.get("method_name")
    timeout = config.get("timeout", 60)

    if not namespace or not method_name:
        return {"result": False, "message": "NATS channel config missing namespace or method_name"}

    try:
        result = nats_client.request_sync(namespace, method_name, _timeout=timeout, _raw=True, **content)
        return result
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": f"NATS request failed: {str(e)}"}
