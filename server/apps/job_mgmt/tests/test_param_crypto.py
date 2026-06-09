"""job_mgmt.services.param_crypto 生产规格测试。

规格：脚本/Playbook 参数的加密字段处理。
- 仅对 is_encrypted=true 且有值的参数加密；
- 加密/解密 default 往返一致；
- mask 用 ****** 隐藏且不修改原始数据；
- 执行参数按定义中的 is_encrypted 加解密往返一致。
依赖 EncryptMixin（settings.SECRET_KEY），不触 DB。
"""

import pytest

from apps.job_mgmt.services.param_crypto import ParamCrypto

pytestmark = pytest.mark.unit


class TestParamDefaults:
    def test_仅加密标记字段且可往返(self):
        params = [
            {"name": "pwd", "default": "secret", "is_encrypted": True},
            {"name": "host", "default": "1.1.1.1", "is_encrypted": False},
        ]
        ParamCrypto.encrypt_param_defaults(params)
        assert params[0]["default"] != "secret"   # 已加密
        assert params[1]["default"] == "1.1.1.1"   # 未动

        ParamCrypto.decrypt_param_defaults(params)
        assert params[0]["default"] == "secret"    # 往返还原

    def test_无default不处理(self):
        params = [{"name": "pwd", "is_encrypted": True}]
        ParamCrypto.encrypt_param_defaults(params)
        assert "default" not in params[0]


class TestMask:
    def test_隐藏加密默认值且不改原数据(self):
        params = [{"name": "pwd", "default": "secret", "is_encrypted": True}]
        masked = ParamCrypto.mask_encrypted_defaults(params)
        assert masked[0]["default"] == "******"
        # 原始数据未被修改
        assert params[0]["default"] == "secret"

    def test_非加密字段不隐藏(self):
        params = [{"name": "host", "default": "1.1.1.1", "is_encrypted": False}]
        masked = ParamCrypto.mask_encrypted_defaults(params)
        assert masked[0]["default"] == "1.1.1.1"


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
