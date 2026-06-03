"""
回调签名工具

为回调请求生成 HMAC-SHA256 签名，用于接收方验证请求来源。
"""

import hashlib
import hmac
import json
import time
from typing import Any

from django.conf import settings


def sign_callback(payload: dict[str, Any], timestamp: int) -> str:
    """
    生成回调签名

    签名算法: HMAC-SHA256(secret_key, timestamp + json(payload))

    Args:
        payload: 回调数据
        timestamp: Unix 时间戳（秒）

    Returns:
        十六进制签名字符串
    """
    # 获取签名密钥（使用 Django SECRET_KEY 或专用配置）
    secret_key = getattr(settings, "CALLBACK_SIGN_KEY", settings.SECRET_KEY)
    if isinstance(secret_key, str):
        secret_key = secret_key.encode("utf-8")

    # 构造签名消息: timestamp + sorted_json(payload)
    # 使用 sort_keys 确保 JSON 序列化结果一致
    message = f"{timestamp}{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"

    # 计算 HMAC-SHA256
    signature = hmac.new(secret_key, message.encode("utf-8"), hashlib.sha256).hexdigest()

    return signature


def get_signed_headers(payload: dict[str, Any]) -> dict[str, str]:
    """
    生成带签名的回调请求头

    Args:
        payload: 回调数据

    Returns:
        包含签名信息的请求头字典:
        - X-BK-Lite-Timestamp: Unix 时间戳
        - X-BK-Lite-Signature: HMAC-SHA256 签名
        - X-BK-Lite-Source: 来源标识
    """
    timestamp = int(time.time())
    signature = sign_callback(payload, timestamp)

    return {
        "X-BK-Lite-Timestamp": str(timestamp),
        "X-BK-Lite-Signature": signature,
        "X-BK-Lite-Source": "bk-lite-job-mgmt",
        "Content-Type": "application/json",
    }


def verify_callback_signature(payload: dict[str, Any], timestamp: int, signature: str, max_age: int = 300) -> bool:
    """
    验证回调签名（供接收方使用）

    Args:
        payload: 回调数据
        timestamp: 请求头中的时间戳
        signature: 请求头中的签名
        max_age: 签名最大有效期（秒），默认 5 分钟

    Returns:
        签名是否有效
    """
    # 检查时间戳是否过期
    current_time = int(time.time())
    if abs(current_time - timestamp) > max_age:
        return False

    # 重新计算签名并比较
    expected_signature = sign_callback(payload, timestamp)
    return hmac.compare_digest(signature, expected_signature)
