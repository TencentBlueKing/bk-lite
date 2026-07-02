import base64
import hashlib
import json
import struct

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCrypto, EnterpriseWechatAibotCryptoError


def _encoding_aes_key() -> str:
    return base64.b64encode(b"0" * 32).decode("utf-8").rstrip("=")


def _signature(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    raw = "".join(sorted([token, timestamp, nonce, encrypted]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _encrypt_json(encoding_aes_key: str, payload: dict) -> str:
    key = base64.b64decode(f"{encoding_aes_key}=")
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    plain = b"1" * 16 + struct.pack("!I", len(content)) + content
    pad = 32 - (len(plain) % 32)
    plain = plain + bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(plain) + encryptor.finalize()).decode("utf-8")


def test_decrypt_callback_rejects_missing_encrypt():
    crypto = EnterpriseWechatAibotCrypto(token="token", encoding_aes_key=_encoding_aes_key())

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="encrypt"):
        crypto.decrypt_callback(
            msg_signature="invalid",
            timestamp="1",
            nonce="nonce",
            body=json.dumps({"msgtype": "text"}).encode("utf-8"),
        )


def test_verify_url_rejects_invalid_signature():
    crypto = EnterpriseWechatAibotCrypto(token="token", encoding_aes_key=_encoding_aes_key())

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="signature"):
        crypto.verify_url(
            msg_signature="invalid",
            timestamp="1",
            nonce="nonce",
            echostr="encrypted",
        )


def test_verify_url_decrypts_echostr():
    token = "token"
    timestamp = "1"
    nonce = "nonce"
    encoding_aes_key = _encoding_aes_key()
    encrypted = _encrypt_json(encoding_aes_key, {"ok": True})
    crypto = EnterpriseWechatAibotCrypto(token=token, encoding_aes_key=encoding_aes_key)

    result = crypto.verify_url(_signature(token, timestamp, nonce, encrypted), timestamp, nonce, encrypted)

    assert result == '{"ok":true}'


def test_decrypt_callback_returns_message_dict():
    token = "token"
    timestamp = "1"
    nonce = "nonce"
    encoding_aes_key = _encoding_aes_key()
    message = {"msgid": "m1", "msgtype": "text", "text": {"content": "hello"}}
    encrypted = _encrypt_json(encoding_aes_key, message)
    crypto = EnterpriseWechatAibotCrypto(token=token, encoding_aes_key=encoding_aes_key)

    result = crypto.decrypt_callback(
        msg_signature=_signature(token, timestamp, nonce, encrypted),
        timestamp=timestamp,
        nonce=nonce,
        body=json.dumps({"encrypt": encrypted}).encode("utf-8"),
    )

    assert result == message


def test_decrypt_callback_rejects_invalid_json_body():
    crypto = EnterpriseWechatAibotCrypto(token="token", encoding_aes_key=_encoding_aes_key())

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="invalid json body"):
        crypto.decrypt_callback("signature", "1", "nonce", b"{")


def test_decrypt_callback_rejects_invalid_message_signature():
    encoding_aes_key = _encoding_aes_key()
    encrypted = _encrypt_json(encoding_aes_key, {"msgid": "m1"})
    crypto = EnterpriseWechatAibotCrypto(token="token", encoding_aes_key=encoding_aes_key)

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="invalid signature"):
        crypto.decrypt_callback("bad-signature", "1", "nonce", json.dumps({"encrypt": encrypted}).encode("utf-8"))


def test_decrypt_callback_rejects_decrypted_non_json():
    token = "token"
    timestamp = "1"
    nonce = "nonce"
    encoding_aes_key = _encoding_aes_key()
    key = base64.b64decode(f"{encoding_aes_key}=")
    content = b"not-json"
    plain = b"1" * 16 + struct.pack("!I", len(content)) + content
    pad = 32 - (len(plain) % 32)
    plain = plain + bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    encryptor = cipher.encryptor()
    encrypted = base64.b64encode(encryptor.update(plain) + encryptor.finalize()).decode("utf-8")
    crypto = EnterpriseWechatAibotCrypto(token=token, encoding_aes_key=encoding_aes_key)

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="invalid decrypted json"):
        crypto.decrypt_callback(
            _signature(token, timestamp, nonce, encrypted),
            timestamp,
            nonce,
            json.dumps({"encrypt": encrypted}).encode("utf-8"),
        )


def test_decrypt_rejects_invalid_encoding_aes_key():
    token = "token"
    timestamp = "1"
    nonce = "nonce"
    encrypted = "encrypted"
    crypto = EnterpriseWechatAibotCrypto(token=token, encoding_aes_key="bad-key")

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="decrypt failed|invalid encoding aes key"):
        crypto.verify_url(_signature(token, timestamp, nonce, encrypted), timestamp, nonce, encrypted)


def test_pkcs7_unpad_rejects_empty_and_invalid_padding():
    with pytest.raises(EnterpriseWechatAibotCryptoError, match="empty plaintext"):
        EnterpriseWechatAibotCrypto._pkcs7_unpad(b"")

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="invalid padding"):
        EnterpriseWechatAibotCrypto._pkcs7_unpad(b"abc" + bytes([33]))
