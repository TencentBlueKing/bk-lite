import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class EnterpriseWechatAibotCryptoError(ValueError):
    pass


@dataclass(frozen=True)
class EnterpriseWechatAibotCrypto:
    token: str
    encoding_aes_key: str

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        if not self._signature_matches(msg_signature, timestamp, nonce, echostr):
            raise EnterpriseWechatAibotCryptoError("invalid signature")
        return self._decrypt(echostr)

    def decrypt_callback(self, msg_signature: str, timestamp: str, nonce: str, body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EnterpriseWechatAibotCryptoError("invalid json body") from exc

        encrypted = payload.get("encrypt")
        if not isinstance(encrypted, str) or not encrypted:
            raise EnterpriseWechatAibotCryptoError("missing encrypt")
        if not self._signature_matches(msg_signature, timestamp, nonce, encrypted):
            raise EnterpriseWechatAibotCryptoError("invalid signature")

        try:
            return json.loads(self._decrypt(encrypted))
        except json.JSONDecodeError as exc:
            raise EnterpriseWechatAibotCryptoError("invalid decrypted json") from exc

    def _signature_matches(self, msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> bool:
        raw = "".join(sorted([self.token, timestamp, nonce, encrypted]))
        expected = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, msg_signature)

    def _aes_key(self) -> bytes:
        try:
            return base64.b64decode(f"{self.encoding_aes_key}=")
        except Exception as exc:
            raise EnterpriseWechatAibotCryptoError("invalid encoding aes key") from exc

    def _decrypt(self, encrypted: str) -> str:
        try:
            key = self._aes_key()
            cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
            decryptor = cipher.decryptor()
            plain = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
            plain = self._pkcs7_unpad(plain)
            content_length = int.from_bytes(plain[16:20], "big")
            content = plain[20 : 20 + content_length]
            return content.decode("utf-8")
        except EnterpriseWechatAibotCryptoError:
            raise
        except Exception as exc:
            raise EnterpriseWechatAibotCryptoError("decrypt failed") from exc

    @staticmethod
    def _pkcs7_unpad(value: bytes) -> bytes:
        if not value:
            raise EnterpriseWechatAibotCryptoError("empty plaintext")
        pad = value[-1]
        if pad < 1 or pad > 32:
            raise EnterpriseWechatAibotCryptoError("invalid padding")
        return value[:-pad]
