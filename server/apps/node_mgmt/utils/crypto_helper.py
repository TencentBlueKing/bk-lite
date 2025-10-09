"""
Django服务端加密工具
用于对API响应数据进行AES-256-GCM加密
"""
import base64
import hashlib
import json
import os
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def uuid_to_key(uuid_str):
    """
    将UUID转换为32字节的AES密钥
    与Go代码中的uuidToKey函数保持一致
    """
    # 移除UUID中的连字符
    clean_uuid = uuid_str.replace('-', '')
    # 使用SHA256将UUID哈希为32字节密钥
    return hashlib.sha256(clean_uuid.encode()).digest()


def encrypt_response_data(data, uuid_str):
    """
    使用UUID加密响应数据

    Args:
        data: 要加密的数据 (dict, list, str 或 bytes)
        uuid_str: UUID字符串，用作加密密钥

    Returns:
        str: Base64编码的加密数据
    """
    try:
        # 如果数据不是bytes，先转换为JSON字符串再编码
        if isinstance(data, (dict, list)):
            plaintext = json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder).encode('utf-8')
        elif isinstance(data, str):
            plaintext = data.encode('utf-8')
        elif isinstance(data, bytes):
            plaintext = data
        else:
            # 其他类型尝试JSON序列化，使用Django编码器处理datetime
            plaintext = json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder).encode('utf-8')

        # 生成32字节AES密钥
        key = uuid_to_key(uuid_str)

        # 使用AES-GCM加密
        aesgcm = AESGCM(key)

        # 生成12字节的nonce (GCM标准)
        nonce = os.urandom(12)

        # 加密数据
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # 组合nonce和密文
        encrypted_data = nonce + ciphertext

        # Base64编码
        return base64.b64encode(encrypted_data).decode('ascii')

    except Exception as e:
        raise Exception(f"Encryption failed: {str(e)}")


class EncryptedJsonResponse(HttpResponse):
    """
    支持加密的JSON响应类
    如果请求包含X-Encryption-Key头，则加密响应数据
    否则返回普通的JSON响应
    """

    def __init__(self, data, request=None, encoder=None, safe=True,
                 json_dumps_params=None, **kwargs):

        # 如果没有指定编码器，默认使用DjangoJSONEncoder处理datetime等对象
        if encoder is None:
            encoder = DjangoJSONEncoder

        # 检查是否需要加密
        encryption_key = None
        if request:
            encryption_key = request.META.get('HTTP_X_ENCRYPTION_KEY')

        if encryption_key:
            # 需要加密
            try:
                encrypted_data = encrypt_response_data(data, encryption_key)
                content = encrypted_data
                kwargs.setdefault("content_type", "application/json")
                kwargs['headers'] = kwargs.get('headers', {})
                kwargs['headers']['Content-Encoding'] = 'encrypted'
            except Exception as e:
                # 加密失败，回退到普通JSON
                if safe and not isinstance(data, dict):
                    raise TypeError(
                        "In order to allow non-dict objects to be serialized set the "
                        "safe parameter to False."
                    )
                if json_dumps_params is None:
                    json_dumps_params = {}
                content = json.dumps(data, cls=encoder, **json_dumps_params)
                kwargs.setdefault("content_type", "application/json")
        else:
            # 不需要加密，使用普通JSON
            if safe and not isinstance(data, dict):
                raise TypeError(
                    "In order to allow non-dict objects to be serialized set the "
                    "safe parameter to False."
                )
            if json_dumps_params is None:
                json_dumps_params = {}
            content = json.dumps(data, cls=encoder, **json_dumps_params)
            kwargs.setdefault("content_type", "application/json")

        super().__init__(content=content, **kwargs)
