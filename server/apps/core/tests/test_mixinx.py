"""core.mixinx.EncryptMixin 纯单元测试。

规格：基于 settings.SECRET_KEY 派生 Fernet 密钥，对字典字段做对称加解密。
安全契约：
- 加密后再解密必须还原明文（往返一致）；
- 解密明文（非密文）走 InvalidToken 分支，保持原值不变（兼容历史明文数据）；
- 缺失/空/非字符串字段不处理；
- 加密结果不等于明文（确实被加密）。
"""

import pytest

from apps.core.mixinx import EncryptMixin

pytestmark = pytest.mark.unit


def test_加密解密往返还原明文():
    d = {"password": "s3cr3t"}
    EncryptMixin.encrypt_field("password", d)
    assert d["password"] != "s3cr3t"  # 确实被加密
    EncryptMixin.decrypt_field("password", d)
    assert d["password"] == "s3cr3t"


def test_解密明文保持不变():
    # 历史明文数据不应被破坏（InvalidToken 分支）
    d = {"password": "plain-text-value"}
    EncryptMixin.decrypt_field("password", d)
    assert d["password"] == "plain-text-value"


@pytest.mark.parametrize(
    "d",
    [
        {},                       # 缺失字段
        {"password": ""},         # 空值
        {"password": None},       # None
        {"password": 12345},      # 非字符串
    ],
)
def test_非法或缺失字段不处理(d):
    snapshot = dict(d)
    EncryptMixin.encrypt_field("password", d)
    assert d == snapshot


def test_get_cipher_suite_可往返():
    suite = EncryptMixin.get_cipher_suite()
    token = suite.encrypt(b"abc")
    assert suite.decrypt(token) == b"abc"
