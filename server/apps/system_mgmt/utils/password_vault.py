from django.conf import settings

from apps.core.utils.crypto.password_crypto import PasswordCrypto


def _get_cipher() -> PasswordCrypto:
    """从 Django settings.SECRET_KEY 派生 AES 密钥;空 key 抛 ValueError。"""
    key = getattr(settings, "SECRET_KEY", "") or ""
    if not key:
        raise ValueError("SECRET_KEY 未配置,无法加解密 vault")
    return PasswordCrypto(key=key)


def encrypt_for_vault(plaintext: str) -> str:
    """加密 UserSyncRun.payload.password_vault 中临时存放的初始密码。"""
    return _get_cipher().encrypt(plaintext)


def decrypt_from_vault(ciphertext: str) -> str:
    """解密 vault 中的密码;失败时抛 ValueError。"""
    return _get_cipher().decrypt(ciphertext)
