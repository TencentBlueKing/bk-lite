import pydantic.root_model  # noqa

import base64

import pytest

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.core.utils.crypto.rsa_crypto import RSACryptor


class TestAESCryptor:
    def test_roundtrip(self):
        c = AESCryptor()
        cipher = c.encode("hello world")
        assert isinstance(cipher, str)
        assert "=" not in cipher  # rstrip("=") 去掉了 base64 填充
        assert c.decode(cipher) == "hello world"

    def test_roundtrip_unicode(self):
        c = AESCryptor()
        assert c.decode(c.encode("中文密码🔒")) == "中文密码🔒"

    def test_encode_empty_raises(self):
        c = AESCryptor()
        with pytest.raises(ValueError):
            c.encode("")

    def test_decode_empty_raises(self):
        c = AESCryptor()
        with pytest.raises(ValueError):
            c.decode("")

    def test_decode_too_short_raises(self):
        c = AESCryptor()
        # urlsafe_b64encode of a few bytes -> decoded len < block_size(16)
        short = base64.urlsafe_b64encode(b"abc").decode().rstrip("=")
        with pytest.raises(ValueError):
            c.decode(short)

    def test_encode_produces_different_ciphertext_each_call(self):
        # CBC 使用随机 IV，相同明文每次密文不同
        c = AESCryptor()
        assert c.encode("same") != c.encode("same")

    def test_decode_pads_base64_when_needed(self):
        c = AESCryptor()
        cipher = c.encode("padding-test-value")
        # encode 已 rstrip("=")，decode 内部应能补齐填充
        assert c.decode(cipher) == "padding-test-value"


class TestPasswordCrypto:
    def test_roundtrip(self):
        pc = PasswordCrypto("my-secret-key")
        token = pc.encrypt("p@ssw0rd")
        assert pc.decrypt(token) == "p@ssw0rd"

    def test_key_padded_to_32_bytes(self):
        pc = PasswordCrypto("short")
        assert len(pc.key) == 32

    def test_key_truncated_to_32_bytes(self):
        pc = PasswordCrypto("x" * 100)
        assert len(pc.key) == 32

    def test_decrypt_strips_and_fixes_padding(self):
        pc = PasswordCrypto("k")
        token = pc.encrypt("value")
        # 去掉 base64 填充后 decrypt 仍能补齐
        stripped = token.rstrip("=")
        assert pc.decrypt("  " + stripped + "  ") == "value"

    def test_decrypt_invalid_raises_value_error(self):
        pc = PasswordCrypto("k")
        with pytest.raises(ValueError):
            pc.decrypt("not-valid-base64-or-cipher!!!")


class TestRSACryptor:
    def test_keys_generated(self):
        r = RSACryptor(bits=1024)
        assert r.private_key and r.public_key

    def test_too_small_key_raises(self):
        with pytest.raises(ValueError):
            RSACryptor(bits=512)

    def test_roundtrip(self):
        r = RSACryptor(bits=1024)
        cipher = r.encrypt_rsa("secret", r.public_key)
        assert r.decrypt_rsa(cipher, r.private_key) == "secret"

    def test_encrypt_empty_plaintext_raises(self):
        r = RSACryptor(bits=1024)
        with pytest.raises(ValueError):
            r.encrypt_rsa("", r.public_key)

    def test_encrypt_empty_public_key_raises(self):
        r = RSACryptor(bits=1024)
        with pytest.raises(ValueError):
            r.encrypt_rsa("x", "")

    def test_encrypt_bad_public_key_raises(self):
        r = RSACryptor(bits=1024)
        with pytest.raises((ValueError, TypeError)):
            r.encrypt_rsa("x", "not-a-key")

    def test_decrypt_empty_text_raises(self):
        r = RSACryptor(bits=1024)
        with pytest.raises(ValueError):
            r.decrypt_rsa("", r.private_key)

    def test_decrypt_empty_private_key_raises(self):
        r = RSACryptor(bits=1024)
        with pytest.raises(ValueError):
            r.decrypt_rsa("abc", "")

    def test_decrypt_bad_private_key_raises(self):
        r = RSACryptor(bits=1024)
        with pytest.raises((ValueError, TypeError)):
            r.decrypt_rsa("abc", "not-a-key")
