from django.test import TestCase, override_settings

from apps.system_mgmt.utils.password_vault import (
    decrypt_from_vault,
    encrypt_for_vault,
)


class PasswordVaultTest(TestCase):
    @override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
    def test_roundtrip(self):
        plain = "MyRandomP@ssw0rd!2026"
        cipher = encrypt_for_vault(plain)
        self.assertNotIn(plain, cipher)
        self.assertEqual(decrypt_from_vault(cipher), plain)

    @override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
    def test_decrypt_invalid_raises(self):
        with self.assertRaises(ValueError):
            decrypt_from_vault("not-a-valid-ciphertext")

    @override_settings(SECRET_KEY="test-secret-key-32bytes-padded!!")
    def test_empty_string_roundtrip(self):
        self.assertEqual(decrypt_from_vault(encrypt_for_vault("")), "")

    def test_missing_secret_key_raises(self):
        """SECRET_KEY 为空字符串时(绕过 Django ImproperlyConfigured),_get_cipher 抛 ValueError。"""
        from unittest import mock

        from apps.system_mgmt.utils import password_vault
        from apps.system_mgmt.utils.i18n import system_mgmt_message

        expected = system_mgmt_message(None, "error.vault_secret_key_not_configured")
        with mock.patch.object(password_vault, "settings", new=mock.Mock(SECRET_KEY="")):
            with self.assertRaises(ValueError) as ctx:
                encrypt_for_vault("anything")
        self.assertEqual(str(ctx.exception), expected)
        self.assertEqual(str(ctx.exception), "SECRET_KEY 未配置,无法加解密 vault")
