"""Issue #3465 的 LoginModuleSerializer 密钥边界回归测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.system_mgmt.models import LoginModule
from apps.system_mgmt.serializers.login_module_serializer import LoginModuleSerializer

pytestmark = pytest.mark.unit


class FakeLoginModule:
    """满足 ModelSerializer 输出所需属性的最小对象。"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "企业微信")
        self.source_type = kwargs.get("source_type", "wechat")
        self.app_id = kwargs.get("app_id", "wx_app_id_123")
        self.app_secret = kwargs.get("app_secret", "ENCRYPTED_CIPHERTEXT_XYZ")
        self.other_config = kwargs.get("other_config", {})
        self.enabled = kwargs.get("enabled", True)
        self.is_build_in = kwargs.get("is_build_in", False)
        self.pk = self.id


class TestLoginModuleSerializerAppSecretNotExposed:
    @staticmethod
    def _make_serializer(instance, method="GET"):
        request = MagicMock()
        request.method = method
        return LoginModuleSerializer(instance, context={"request": request})

    def test_app_secret_not_in_serializer_output(self):
        instance = FakeLoginModule(app_secret="ENCRYPTED_CIPHER_SECRET")
        serializer = self._make_serializer(instance)

        data = serializer.to_representation(instance)

        assert "app_secret" not in data

    def test_non_secret_fields_still_present(self):
        instance = FakeLoginModule(
            name="企业微信登录",
            source_type="wechat",
            app_id="wx123",
            enabled=True,
        )
        serializer = self._make_serializer(instance)

        data = serializer.to_representation(instance)

        assert {"name", "source_type", "app_id", "enabled"} <= data.keys()

    def test_app_secret_field_is_write_only_and_optional(self):
        field = LoginModuleSerializer().fields["app_secret"]

        assert field.write_only is True
        assert field.required is False


class TestLoginModuleSerializerUpdatePreservesSecret:
    @staticmethod
    def _update(existing_cipher, validated_data):
        instance = LoginModule(
            name="企业微信",
            source_type="wechat",
            app_secret=existing_cipher,
            other_config={},
        )
        serializer = LoginModuleSerializer()
        with patch.object(instance, "save") as save:
            updated = serializer.update(instance, validated_data)
        save.assert_called_once_with()
        return updated

    def test_update_preserves_existing_app_secret_when_not_in_payload(self):
        existing_cipher = "gAAAAAB_EXISTING_CIPHER"

        updated = self._update(existing_cipher, {"name": "新名称"})

        assert updated.app_secret == existing_cipher

    def test_update_preserves_existing_app_secret_when_null(self):
        existing_cipher = "gAAAAAB_EXISTING_CIPHER"

        updated = self._update(existing_cipher, {"app_secret": None})

        assert updated.app_secret == existing_cipher

    def test_update_preserves_existing_app_secret_when_blank(self):
        existing_cipher = "gAAAAAB_EXISTING_CIPHER"

        updated = self._update(existing_cipher, {"app_secret": ""})

        assert updated.app_secret == existing_cipher

    def test_update_uses_provided_app_secret_when_in_payload(self):
        updated = self._update(
            "gAAAAAB_OLD_CIPHER",
            {"name": "企业微信", "app_secret": "new_plain_secret"},
        )

        assert updated.app_secret == "new_plain_secret"
