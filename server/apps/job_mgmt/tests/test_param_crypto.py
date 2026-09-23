"""job_mgmt.services.param_crypto 生产规格测试。

规格：脚本/Playbook 参数的加密字段处理。
- 仅对 is_encrypted=true 且有值的参数加密；
- 加密/解密 default 往返一致；
- mask 用 ****** 隐藏且不修改原始数据；
- 更新收到掩码时沿用原密文，不把 ****** 当明文二次加密；
- 执行参数按定义中的 is_encrypted 加解密往返一致。
依赖 EncryptMixin（settings.SECRET_KEY），不触 DB。
"""

import pytest

from apps.job_mgmt.services.param_crypto import MASKED_DEFAULT, ParamCrypto

pytestmark = pytest.mark.unit


class TestParamDefaults:
    def test_仅加密标记字段且可往返(self):
        params = [
            {"name": "pwd", "default": "secret", "is_encrypted": True},
            {"name": "host", "default": "1.1.1.1", "is_encrypted": False},
        ]
        ParamCrypto.encrypt_param_defaults(params)
        assert params[0]["default"] != "secret"  # 已加密
        assert params[1]["default"] == "1.1.1.1"  # 未动

        ParamCrypto.decrypt_param_defaults(params)
        assert params[0]["default"] == "secret"  # 往返还原

    def test_无default不处理(self):
        params = [{"name": "pwd", "is_encrypted": True}]
        ParamCrypto.encrypt_param_defaults(params)
        assert "default" not in params[0]

    def test_创建时掩码不当明文落库(self):
        params = [{"name": "pwd", "default": MASKED_DEFAULT, "is_encrypted": True}]
        ParamCrypto.encrypt_param_defaults(params)
        assert params[0]["default"] == ""


class TestMask:
    def test_隐藏加密默认值且不改原数据(self):
        params = [{"name": "pwd", "default": "secret", "is_encrypted": True}]
        masked = ParamCrypto.mask_encrypted_defaults(params)
        assert masked[0]["default"] == MASKED_DEFAULT
        # 原始数据未被修改
        assert params[0]["default"] == "secret"

    def test_非加密字段不隐藏(self):
        params = [{"name": "host", "default": "1.1.1.1", "is_encrypted": False}]
        masked = ParamCrypto.mask_encrypted_defaults(params)
        assert masked[0]["default"] == "1.1.1.1"


class TestPreserveMaskedOnSave:
    def test_更新掩码沿用原密文且可解密(self):
        existing = [{"name": "pwd", "default": "test123456", "is_encrypted": True}]
        ParamCrypto.encrypt_param_defaults(existing)
        ciphertext = existing[0]["default"]
        assert ciphertext != "test123456"
        assert ciphertext != MASKED_DEFAULT

        incoming = [
            {"name": "pwd", "default": MASKED_DEFAULT, "is_encrypted": True},
            {"name": "hint", "default": "changed", "is_encrypted": False},
        ]
        ParamCrypto.prepare_param_defaults_for_save(incoming, existing_params=existing)

        assert incoming[0]["default"] == ciphertext
        assert incoming[1]["default"] == "changed"

        ready = ParamCrypto.prepare_params_for_execution({}, incoming)
        assert ready["pwd"] == "test123456"

    def test_更新提交新明文会覆盖原密文(self):
        existing = [{"name": "pwd", "default": "old-secret", "is_encrypted": True}]
        ParamCrypto.encrypt_param_defaults(existing)

        incoming = [{"name": "pwd", "default": "new-secret", "is_encrypted": True}]
        ParamCrypto.prepare_param_defaults_for_save(incoming, existing_params=existing)

        assert incoming[0]["default"] != "new-secret"
        assert incoming[0]["default"] != existing[0]["default"]
        ParamCrypto.decrypt_param_defaults(incoming)
        assert incoming[0]["default"] == "new-secret"

    def test_掩码但无同名原参数时清空(self):
        incoming = [{"name": "pwd", "default": MASKED_DEFAULT, "is_encrypted": True}]
        ParamCrypto.prepare_param_defaults_for_save(incoming, existing_params=[])
        assert incoming[0]["default"] == ""


class TestExecutionParams:
    def test_执行参数加解密往返(self):
        definitions = [
            {"name": "pwd", "is_encrypted": True},
            {"name": "host", "is_encrypted": False},
        ]
        params = {"pwd": "secret", "host": "1.1.1.1"}
        ParamCrypto.encrypt_execution_params(params, definitions)
        assert params["pwd"] != "secret"
        assert params["host"] == "1.1.1.1"

        ParamCrypto.decrypt_execution_params(params, definitions)
        assert params["pwd"] == "secret"

    def test_空输入安全返回(self):
        assert ParamCrypto.encrypt_execution_params({}, []) == {}
        assert ParamCrypto.mask_encrypted_defaults([]) == []
