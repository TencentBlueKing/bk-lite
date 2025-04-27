import base64
import hashlib
import os

from cryptography.fernet import Fernet


class Credential:
    def __init__(self):
        self.fernet = self.get_fernet()

    def get_key(self):
        """获取fernet需要的密钥key"""
        # 获取环境变量中的密钥
        credential_key = os.getenv("SECRET_KEY")
        # 将字符串转换为字节类型
        custom_key_bytes = credential_key.encode("utf-8")
        # 使用SHA-256哈希函数将其转换为32字节的哈希值
        custom_key_bytes_32 = hashlib.sha256(custom_key_bytes).digest()
        # 将自定义密钥编码为 URL 安全的 Base64 格式
        encoded_key = base64.urlsafe_b64encode(custom_key_bytes_32)
        return encoded_key

    def get_fernet(self):
        """获取fernet对象"""
        credential_key = self.get_key()
        return Fernet(credential_key)

    def encrypt_data(self, data: str):
        """加密"""
        return self.fernet.encrypt(data.encode("utf-8")).decode()

    def decrypt_data(self, data: str):
        """解密"""
        return self.fernet.decrypt(data.encode("utf-8")).decode()
