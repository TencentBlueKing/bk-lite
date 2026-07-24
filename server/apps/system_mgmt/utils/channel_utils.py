import base64
import hashlib
import hmac
import ipaddress
import json
import re
import smtplib
import socket
import time
import urllib.parse
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import unquote, urlparse

import requests
from wechatpy import WeChatClientException
from wechatpy.enterprise import WeChatClient

import nats_client
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Channel
from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs, get_network_whitelist_domains


def is_valid_webhook_url(url: str) -> bool:
    """验证 Webhook URL 是否命中出站白名单,防止 SSRF 攻击。

    判定流程(短路求值):
    1. URL 基础校验:scheme ∈ {http, https},无反斜杠/userinfo/编码绕过。
    2. hostname 小写后命中 `NetworkWhiteList.domain`(字符串等值)。
    3. 否则解析 hostname → IP,所有 IP 均落在 `NetworkWhiteList.network` CIDR 内才放行。
    4. 全部不命中 → 拒绝,日志记录 hostname + 解析 IP 列表(fail-closed)。

    Args:
        url: Webhook URL

    Returns:
        bool: URL 是否有效且命中白名单
    """
    if not url:
        return False
    try:
        # 拒绝含反斜杠的 URL(urlparse 与 requests 解析不一致,可绕过域名校验)
        if "\\" in url:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return False
        # 拒绝含 userinfo(@)的 URL,防止 user@host 形式的绕过
        if "@" in (parsed.netloc or ""):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # 对 hostname 解码后校验,防止 %23 %00 等编码绕过
        decoded_hostname = unquote(hostname).lower()
        if decoded_hostname != hostname.lower():
            return False
        # hostname 只允许字母、数字、连字符、点号
        if not re.match(r"^[a-z0-9\-\.]+$", hostname.lower()):
            return False
        hostname_lower = hostname.lower()

        # 路径 1:domain 集等值匹配(不做 DNS 解析,避免 rebinding)
        allowed_domains = {d.lower() for d in get_network_whitelist_domains()}
        if hostname_lower in allowed_domains:
            return True

        # 路径 2:解析 hostname 到 IP,所有 IP 均落入白名单 CIDR → 通过
        allowed_cidrs = get_network_whitelist_cidrs()
        if allowed_cidrs:
            allowed_networks = []
            for cidr in allowed_cidrs:
                try:
                    allowed_networks.append(ipaddress.ip_network(cidr, strict=False))
                except ValueError:
                    continue
            if not allowed_networks:
                return False

            resolved_ips: list[str] = []
            resolved_ip_objects: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
            try:
                infos = socket.getaddrinfo(hostname, None)
            except (socket.gaierror, UnicodeError, OSError) as exc:
                logger.warning(f"[SSRF] DNS 解析失败: hostname={hostname_lower}, error={exc}")
                return False
            for info in infos:
                sockaddr = info[4]
                if not sockaddr:
                    continue
                ip_str = sockaddr[0]
                # 去除 IPv6 方括号
                ip_str = ip_str.strip("[]")
                resolved_ips.append(ip_str)
                try:
                    ip_obj = ipaddress.ip_address(ip_str)
                except ValueError:
                    logger.warning(f"[SSRF] DNS 返回非法 IP: hostname={hostname_lower}, ip={ip_str}")
                    return False
                resolved_ip_objects.append(ip_obj)
            if resolved_ip_objects and all(any(ip_obj in allowed_network for allowed_network in allowed_networks) for ip_obj in resolved_ip_objects):
                return True
            logger.warning(f"[SSRF] 阻断 webhook URL: hostname={hostname_lower}, resolved_ips={resolved_ips}")
        return False
    except Exception as exc:
        logger.exception(f"[SSRF] webhook 校验异常: {exc}")
        return False


def _webhook_hostname(url: str) -> str:
    """返回可安全记录的 hostname,避免 path/query 中的 token 泄露到日志。"""
    try:
        return urlparse(url).hostname or "<invalid>"
    except ValueError:
        return "<invalid>"


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


def send_personalized_email_messages(channel_obj: Channel, messages: list[dict], timeout: int = 30) -> dict:
    """复用 SMTP 连接发送多封不同正文的邮件，仅供内部批任务调用。"""
    channel_config = dict(channel_obj.config or {})
    channel_obj.decrypt_field("smtp_pwd", channel_config)
    server = None
    results = {}
    try:
        if channel_config.get("smtp_usessl", False):
            server = smtplib.SMTP_SSL(channel_config["smtp_server"], channel_config["port"], timeout=timeout)
        else:
            server = smtplib.SMTP(channel_config["smtp_server"], channel_config["port"], timeout=timeout)
        if channel_config.get("smtp_usetls", False):
            server.starttls()
        server.login(channel_config["smtp_user"], channel_config["smtp_pwd"])
        for item in messages:
            msg = MIMEMultipart()
            msg["From"] = channel_config["mail_sender"]
            msg["To"] = item["receiver"]
            msg["Subject"] = item["title"]
            msg.attach(MIMEText(item["content"], "html", "utf-8"))
            try:
                server.send_message(msg)
                results[item["key"]] = {"result": True}
            except (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
                # 连接级错误由批任务租约恢复，不将未尝试用户误记为终态失败。
                raise
            except smtplib.SMTPException as exc:
                results[item["key"]] = {"result": False, "message": str(exc)}
        return results
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


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
                header_filename = filename if filename.isascii() else Header(filename, "utf-8").encode()
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=header_filename,
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


def send_by_wecom_bot(channel_obj: Channel, content, receivers):
    if receivers:
        to_user_mentions = " ".join(f"@{name} " for name in receivers)
        content = f"{content}\nTo: {to_user_mentions}"
    channel_config = channel_obj.config
    payload = {"msgtype": "markdown", "markdown": {"content": content}}

    # 优先使用 webhook_url（通用 webhook）
    channel_obj.decrypt_field("webhook_url", channel_config)
    webhook_url = channel_config.get("webhook_url")
    if not webhook_url:
        channel_obj.decrypt_field("bot_key", channel_config)
        bot_key = channel_config.get("bot_key")
        webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={bot_key}"

    # SSRF 防护：验证 webhook URL 域名
    if not is_valid_webhook_url(webhook_url):
        logger.warning(f"[SSRF] 阻断非法 webhook hostname: {_webhook_hostname(webhook_url)}")
        return {"result": False, "message": "webhook domain or IP not in whitelist"}

    try:
        res = requests.post(webhook_url, json=payload, timeout=5, allow_redirects=False)
        return res.json()
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": "failed to send bot message"}


def send_by_feishu_bot(channel_obj: Channel, title, content, receivers):
    """发送飞书机器人消息（interactive 卡片格式，支持 Markdown，可选 HMAC-SHA256 签名）"""
    if receivers:
        to_user_mentions = " ".join(f"@{name} " for name in receivers)
        content = f"{content}\nTo: {to_user_mentions}"
    channel_config = channel_obj.config
    channel_obj.decrypt_field("webhook_url", channel_config)
    webhook_url = channel_config.get("webhook_url")
    if not webhook_url:
        return {"result": False, "message": "Feishu bot webhook_url is not configured"}

    # SSRF 防护：验证 webhook URL 域名
    if not is_valid_webhook_url(webhook_url):
        logger.warning(f"[SSRF] 阻断非法 webhook hostname: {_webhook_hostname(webhook_url)}")
        return {"result": False, "message": "webhook domain or IP not in whitelist"}

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title or "\u901a\u77e5"}},
            "elements": [{"tag": "markdown", "content": content}],
        },
    }

    # 可选签名验证（秒级时间戳）
    channel_obj.decrypt_field("sign_secret", channel_config)
    sign_secret = channel_config.get("sign_secret")
    if sign_secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{sign_secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        payload["timestamp"] = timestamp
        payload["sign"] = sign

    try:
        res = requests.post(webhook_url, json=payload, timeout=5, allow_redirects=False)
        return res.json()
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": "failed to send feishu bot message"}


def send_by_dingtalk_bot(channel_obj: Channel, title, content, receivers):
    """发送钉钉机器人消息（markdown 格式，可选 HMAC-SHA256 签名）"""
    # at_mobiles = []
    if receivers:
        to_user_mentions = " ".join(f"@{name} " for name in receivers)
        content = f"{content}<br>To: {to_user_mentions}"
    channel_config = channel_obj.config
    channel_obj.decrypt_field("webhook_url", channel_config)
    webhook_url = channel_config.get("webhook_url")
    if not webhook_url:
        return {"result": False, "message": "DingTalk bot webhook_url is not configured"}

    # SSRF protection: validate webhook URL against allowlist before signing
    if not is_valid_webhook_url(webhook_url):
        logger.warning(f"[SSRF] 阻断非法 webhook hostname: {_webhook_hostname(webhook_url)}")
        return {"result": False, "message": "webhook domain or IP not in whitelist"}

    # 可选签名验证（毫秒级时间戳，URL 编码）
    channel_obj.decrypt_field("sign_secret", channel_config)
    sign_secret = channel_config.get("sign_secret")
    if sign_secret:
        timestamp = str(int(round(time.time() * 1000)))
        string_to_sign = f"{timestamp}\n{sign_secret}"
        hmac_code = hmac.new(sign_secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
        webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title or "\u901a\u77e5", "text": content},
        # "at": {"atMobiles": at_mobiles},
    }

    try:
        res = requests.post(webhook_url, json=payload, timeout=5, allow_redirects=False)
        return res.json()
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": "failed to send dingtalk bot message"}


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
    bot_id = config.get("bot_id")
    node_id = config.get("node_id")
    timeout = config.get("timeout", 60)

    if not namespace or not method_name:
        return {"result": False, "message": "NATS channel config missing namespace or method_name"}

    payload = dict(content)
    if method_name == "trigger_workflow_by_nats":
        if bot_id is None or not node_id:
            return {"result": False, "message": "NATS channel config missing bot_id or node_id"}
        payload.update({"bot_id": bot_id, "node_id": node_id})

    try:
        result = nats_client.request_sync(namespace, method_name, _timeout=timeout, _raw=True, **payload)
        return result
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": f"NATS request failed: {str(e)}"}


def send_by_custom_webhook(channel_obj: Channel, content, receivers):
    """发送自定义 Webhook 消息，body_template 中的 {{content}} 被替换为实际内容"""
    channel_config = channel_obj.config
    channel_obj.decrypt_field("webhook_url", channel_config)
    webhook_url = channel_config.get("webhook_url")
    if not webhook_url:
        return {"result": False, "message": "Custom webhook url is not configured"}
    if not is_valid_webhook_url(webhook_url):
        return {"result": False, "message": "webhook domain or IP not in whitelist"}
    if receivers:
        to_user_mentions = " ".join(f"@{name} " for name in receivers)
        content = f"{content}<br>To: {to_user_mentions}"
    body_template = channel_config.get("body_template", "")
    request_method = channel_config.get("request_method", "POST").upper()

    try:
        headers = json.loads(channel_config.get("headers")) or {}
    except (json.JSONDecodeError, TypeError):
        headers = {}

    body_str = ""
    try:
        body = _replace_placeholder(json.loads(body_template), "{{content}}", content)
    except (json.JSONDecodeError, TypeError):
        body = None
        body_str = body_template.replace("{{content}}", content)
    try:
        if body is not None:
            res = requests.request(
                request_method,
                webhook_url,
                json=body,
                headers=headers,
                timeout=10,
                allow_redirects=False,
            )
        else:
            headers.setdefault("Content-Type", "text/plain")
            res = requests.request(
                request_method,
                webhook_url,
                data=body_str.encode("utf-8"),
                headers=headers,
                timeout=10,
                allow_redirects=False,
            )
        return res.json()
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": "failed to send custom webhook message"}


# 先解析模板为结构体，再递归替换 {{content}}，避免 content 中的换行符等破坏 JSON 语法
def _replace_placeholder(obj, placeholder, value):
    if isinstance(obj, str):
        return obj.replace(placeholder, value)
    if isinstance(obj, dict):
        return {k: _replace_placeholder(v, placeholder, value) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_placeholder(i, placeholder, value) for i in obj]
    return obj
