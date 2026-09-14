import hashlib
from base64 import urlsafe_b64decode, urlsafe_b64encode

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from apps.core.logger import logger
from config.components.base import SECRET_KEY


class AESCryptor:
    def __init__(self):
        if not SECRET_KEY:
            raise ValueError("SECRET_KEY 不能为空")

        # 使用SHA256代替MD5提升安全性
        self.__key = hashlib.sha256(SECRET_KEY.encode("utf8")).digest()[:32]

    def encode(self, plaintext):
        """AES encryption"""
        if not plaintext:
            raise ValueError("待加密文本不能为空")

        try:
            cipher = AES.new(self.__key, AES.MODE_CBC)
            ciphertext = cipher.encrypt(pad(plaintext.encode("utf8"), AES.block_size))
            result = urlsafe_b64encode(cipher.iv + ciphertext).decode("utf8").rstrip("=")
            return result
        except Exception as e:
            logger.error(f"AES 编码失败: {e}")
            raise

    def _decrypt(self, ciphertext):
        if not ciphertext:
            raise ValueError("待解密文本不能为空")
        padding_needed = 4 - len(ciphertext) % 4
        if padding_needed != 4:
            ciphertext += "=" * padding_needed
        decoded_data = urlsafe_b64decode(ciphertext)
        if len(decoded_data) < AES.block_size:
            raise ValueError("加密数据格式错误：长度不足")
        iv = decoded_data[: AES.block_size]
        actual_ciphertext = decoded_data[AES.block_size :]
        cipher = AES.new(self.__key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(actual_ciphertext), AES.block_size).decode("utf8")

    def decode(self, ciphertext):
        """AES decryption"""
        try:
            return self._decrypt(ciphertext)
        except Exception as e:
            logger.error(f"AES 解码失败: {e}")
            raise

    def try_decode(self, ciphertext):
        """解密失败返回 None，不打错误日志（表单可能传来明文 SecretKey）。"""
        try:
            return self._decrypt(ciphertext)
        except Exception:
            return None
