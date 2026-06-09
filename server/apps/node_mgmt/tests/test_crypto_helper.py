"""node_mgmt.utils.crypto_helper 生产规格测试。

规格：对 API 响应做 AES-256-GCM 加密，密钥由 UUID 经 SHA256 派生（与 Go 端一致）。
- uuid_to_key 确定性、忽略连字符、产出 32 字节；
- encrypt_response_data 产出 Base64(nonce(12)+ciphertext)，可用同密钥解密还原。
"""

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.node_mgmt.utils.crypto_helper import encrypt_response_data, uuid_to_key

pytestmark = pytest.mark.unit

UUID = "12345678-1234-1234-1234-123456789abc"


class TestUuidToKey:
    def test_确定性且32字节(self):
        k1 = uuid_to_key(UUID)
        k2 = uuid_to_key(UUID)
        assert k1 == k2
        assert len(k1) == 32

    def test_忽略连字符(self):
        assert uuid_to_key(UUID) == uuid_to_key(UUID.replace("-", ""))

    def test_与sha256定义一致(self):
        expected = hashlib.sha256(UUID.replace("-", "").encode()).digest()
        assert uuid_to_key(UUID) == expected


class TestEncryptResponseData:
    def _decrypt(self, b64):
        raw = base64.b64decode(b64)
        nonce, ciphertext = raw[:12], raw[12:]
        return AESGCM(uuid_to_key(UUID)).decrypt(nonce, ciphertext, None)

    def test_dict_往返(self):
        data = {"a": 1, "b": "中文"}
        enc = encrypt_response_data(data, UUID)
        assert json.loads(self._decrypt(enc)) == data

    def test_str_往返(self):
        enc = encrypt_response_data("hello", UUID)
        assert self._decrypt(enc) == b"hello"

    def test_每次nonce不同导致密文不同(self):
        a = encrypt_response_data("x", UUID)
        b = encrypt_response_data("x", UUID)
        assert a != b  # 随机 nonce 保证语义安全
