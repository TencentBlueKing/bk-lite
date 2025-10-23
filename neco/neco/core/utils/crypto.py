from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64


class PasswordCrypto:
    def __init__(self, key: str):
        # 确保密钥长度为 16, 24 或 32 字节
        self.key = key.encode('utf-8').ljust(32)[:32]
        self.mode = AES.MODE_CBC

    def encrypt(self, plaintext: str) -> str:
        cipher = AES.new(self.key, self.mode)
        iv = cipher.iv  # 初始化向量
        ciphertext = cipher.encrypt(
            pad(plaintext.encode('utf-8'), AES.block_size))
        # 返回 base64 编码的 iv 和密文
        return base64.b64encode(iv + ciphertext).decode('utf-8')

    def decrypt(self, encrypted_text: str) -> str:
        # 修复 base64 填充问题
        encrypted_text = encrypted_text.strip()
        missing_padding = len(encrypted_text) % 4
        if missing_padding:
            encrypted_text += '=' * (4 - missing_padding)

        try:
            data = base64.b64decode(encrypted_text)
            iv = data[:AES.block_size]  # 提取 iv
            ciphertext = data[AES.block_size:]
            cipher = AES.new(self.key, self.mode, iv)
            plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
            return plaintext.decode('utf-8')
        except Exception as e:
            raise ValueError(f"解密失败: {str(e)}")
