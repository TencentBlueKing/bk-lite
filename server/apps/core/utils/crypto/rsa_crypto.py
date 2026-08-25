import base64

from apps.core.logger import logger
from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA


class RSACryptor:
    DEFAULT_KEY_SIZE = 2048
    MIN_KEY_SIZE = 1024

    def __init__(self, bits=DEFAULT_KEY_SIZE):
        if bits < self.MIN_KEY_SIZE:
            raise ValueError(f"密钥长度不能小于 {self.MIN_KEY_SIZE} 位")

        try:
            self.key = RSA.generate(bits)
            self.private_key = self.key.export_key()
            self.public_key = self.key.publickey().export_key()
            logger.info("RSA 密钥对生成成功，长度: %s 位", bits)
        except Exception as e:
            logger.error(f"RSA 密钥生成失败: {e}")
            raise

    def encrypt_rsa(self, plain_text, public_key):
        if not plain_text:
            raise ValueError("待加密文本不能为空")
        if not public_key:
            raise ValueError("公钥不能为空")

        try:
            rsakey = RSA.import_key(public_key)
            cipher = PKCS1_OAEP.new(rsakey)
            encrypted_text = cipher.encrypt(plain_text.encode("utf-8"))
            return base64.b64encode(encrypted_text).decode("utf-8")
        except (ValueError, TypeError) as e:
            logger.error(f"RSA 加密失败，密钥格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"RSA 加密失败: {e}")
            raise

    def decrypt_rsa(self, encrypted_text, private_key):
        if not encrypted_text:
            raise ValueError("待解密文本不能为空")
        if not private_key:
            raise ValueError("私钥不能为空")

        try:
            rsakey = RSA.import_key(private_key)
            cipher = PKCS1_OAEP.new(rsakey)
            decoded_data = base64.b64decode(encrypted_text.encode("utf-8"))
            return cipher.decrypt(decoded_data).decode("utf-8")
        except (ValueError, TypeError) as e:
            logger.error(f"RSA 解密失败，密钥或数据格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"RSA 解密失败: {e}")
            raise
