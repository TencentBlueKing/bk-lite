"""system_mgmt.utils.password_validator 生产规格测试。

规格：依据 SystemSettings 中的密码策略（pwd_set_*）校验密码复杂度。
无策略行时使用默认策略（min8/max20/四类字符必含）。安全相关，必须可靠。
经真实 DB 验证（策略读取 + 校验规则）。
"""

import pytest

from apps.system_mgmt.models import SystemSettings
from apps.system_mgmt.utils.password_validator import PasswordValidator

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDefaultPolicy:
    """无 SystemSettings 行 -> 默认策略。"""

    def test_合法密码通过(self):
        ok, msg = PasswordValidator.validate_password("Abcd123!")
        assert ok is True
        assert msg == ""

    def test_空密码拒绝(self):
        ok, msg = PasswordValidator.validate_password("")
        assert ok is False
        assert "不能为空" in msg

    def test_过短拒绝(self):
        ok, msg = PasswordValidator.validate_password("Ab1!")
        assert ok is False
        assert "不能少于" in msg

    def test_过长拒绝(self):
        ok, msg = PasswordValidator.validate_password("Abcd123!" * 3)
        assert ok is False
        assert "不能超过" in msg

    @pytest.mark.parametrize("pwd,missing", [
        ("abcd123!", "大写字母"),
        ("ABCD123!", "小写字母"),
        ("Abcdefg!", "数字"),
        ("Abcd1234", "特殊符号"),
    ])
    def test_缺失字符类型拒绝(self, pwd, missing):
        ok, msg = PasswordValidator.validate_password(pwd)
        assert ok is False
        assert missing in msg

    def test_非ascii字符拒绝(self):
        ok, msg = PasswordValidator.validate_password("Abcd123!密码")
        assert ok is False
        assert "非法字符" in msg


class TestCustomPolicy:
    """自定义 SystemSettings 策略生效。"""

    def test_读取并应用自定义策略(self):
        # 迁移可能已 seed 默认 pwd_set_* 行，这里用 update_or_create 覆盖为自定义策略
        SystemSettings.objects.update_or_create(key="pwd_set_min_length", defaults={"value": "4"})
        SystemSettings.objects.update_or_create(key="pwd_set_max_length", defaults={"value": "6"})
        SystemSettings.objects.update_or_create(
            key="pwd_set_required_char_types", defaults={"value": "lowercase,digit"}
        )

        config = PasswordValidator.get_password_settings()
        assert config["min_length"] == 4
        assert config["max_length"] == 6
        assert config["required_char_types"] == ["lowercase", "digit"]

        # 仅需小写+数字，长度 4-6
        ok, _ = PasswordValidator.validate_password("ab12")
        assert ok is True
        # 超过 max_length=6
        ok, msg = PasswordValidator.validate_password("abc1234")
        assert ok is False and "不能超过" in msg
