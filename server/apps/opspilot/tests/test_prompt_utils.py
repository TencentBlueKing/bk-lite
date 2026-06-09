"""opspilot.utils.prompt_utils 生产规格测试。

规格(技能参数/密码处理，此前仅被 mock，从未真测)：
- resolve_skill_params：将 {{key}} 替换为参数值；password 类型先解密；空输入安全返回；
- merge_skill_params：前端空→用 DB；password 值为 '******'→取回 DB 密文；
  password 新明文→保留前端；非 password→用前端值。
依赖 EncryptMixin(settings.SECRET_KEY)，不触 DB。
"""

import pytest

from apps.core.mixinx import EncryptMixin
from apps.opspilot.utils.prompt_utils import (
    MASK_VALUE,
    merge_skill_params,
    resolve_skill_params,
)

pytestmark = pytest.mark.unit


class TestResolveSkillParams:
    def test_普通参数替换占位符(self):
        prompt = "host={{host}} port={{port}}"
        params = [
            {"key": "host", "value": "1.1.1.1", "type": "string"},
            {"key": "port", "value": 8080, "type": "string"},
        ]
        assert resolve_skill_params(prompt, params) == "host=1.1.1.1 port=8080"

    def test_password类型先解密再替换(self):
        enc = {"value": "secret"}
        EncryptMixin.encrypt_field("value", enc)  # 加密成密文
        params = [{"key": "pwd", "value": enc["value"], "type": "password"}]
        assert resolve_skill_params("p={{pwd}}", params) == "p=secret"

    def test_空输入安全返回(self):
        assert resolve_skill_params("", [{"key": "a", "value": "b"}]) == ""
        assert resolve_skill_params("text", []) == "text"


class TestMergeSkillParams:
    def test_前端为空用db(self):
        db = [{"key": "a", "value": "x", "type": "string"}]
        assert merge_skill_params([], db) == db

    def test_掩码密码取回db密文(self):
        frontend = [{"key": "pwd", "value": MASK_VALUE, "type": "password"}]
        db = [{"key": "pwd", "value": "ENCRYPTED", "type": "password"}]
        merged = merge_skill_params(frontend, db)
        assert merged[0]["value"] == "ENCRYPTED"

    def test_新明文密码保留前端(self):
        frontend = [{"key": "pwd", "value": "newplain", "type": "password"}]
        db = [{"key": "pwd", "value": "OLD", "type": "password"}]
        merged = merge_skill_params(frontend, db)
        assert merged[0]["value"] == "newplain"

    def test_非密码参数用前端值(self):
        frontend = [{"key": "host", "value": "2.2.2.2", "type": "string"}]
        db = [{"key": "host", "value": "1.1.1.1", "type": "string"}]
        assert merge_skill_params(frontend, db)[0]["value"] == "2.2.2.2"

    def test_不修改前端原对象(self):
        frontend = [{"key": "pwd", "value": MASK_VALUE, "type": "password"}]
        db = [{"key": "pwd", "value": "ENC", "type": "password"}]
        merge_skill_params(frontend, db)
        assert frontend[0]["value"] == MASK_VALUE  # deepcopy 保护
