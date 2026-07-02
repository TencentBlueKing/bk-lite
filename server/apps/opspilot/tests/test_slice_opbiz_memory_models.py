"""opspilot-biz 切片: models/memory_mgmt.MemorySpace 真实 DB 行为测试。

覆盖 save 时对 storage_config.api_key 加密、get_decrypted_config 还原、
get_masked_config 脱敏（密文→***，明文长串→前3位+***，短串→***）。
"""

import pytest

from apps.opspilot.models.memory_mgmt import MemorySpace

pytestmark = pytest.mark.django_db


def _make_space(storage_config):
    return MemorySpace.objects.create(
        name="space",
        team=[1],
        storage_type=MemorySpace.STORAGE_CUSTOM,
        storage_config=storage_config,
    )


class TestMemorySpaceEncryption:
    def test_save_加密api_key(self):
        sp = _make_space({"api_key": "sk-mem", "endpoint": "https://x"})
        sp.refresh_from_db()
        assert sp.storage_config["api_key"] != "sk-mem"
        assert sp.storage_config["api_key"].startswith("gAAAAA")
        # 非加密字段保持原值
        assert sp.storage_config["endpoint"] == "https://x"

    def test_get_decrypted_config还原(self):
        sp = _make_space({"api_key": "sk-mem", "endpoint": "https://x"})
        sp.refresh_from_db()
        cfg = sp.get_decrypted_config()
        assert cfg["api_key"] == "sk-mem"
        assert cfg["endpoint"] == "https://x"

    def test_save_不重复加密(self):
        sp = _make_space({"api_key": "sk-once"})
        first = sp.storage_config["api_key"]
        sp.save()
        sp.refresh_from_db()
        assert sp.get_decrypted_config()["api_key"] == "sk-once"
        assert sp.storage_config["api_key"] == first

    def test_空配置(self):
        sp = _make_space({})
        sp.refresh_from_db()
        assert sp.get_decrypted_config() == {}
        assert sp.get_masked_config() == {}

    def test_无api_key字段不变(self):
        sp = _make_space({"endpoint": "https://x"})
        sp.refresh_from_db()
        assert sp.storage_config == {"endpoint": "https://x"}


class TestMemorySpaceMasked:
    def test_密文掩码为三星(self):
        sp = _make_space({"api_key": "sk-secret-value"})
        sp.refresh_from_db()
        # 落库后 api_key 是密文 → 掩码为 ***
        assert sp.get_masked_config()["api_key"] == "***"

    def test_明文长串前缀加星(self):
        # 直接构造未落库实例，api_key 为明文长串
        sp = MemorySpace(storage_config={"api_key": "abcdefgh"})
        assert sp.get_masked_config()["api_key"] == "abc***"

    def test_明文短串全掩码(self):
        sp = MemorySpace(storage_config={"api_key": "ab"})
        assert sp.get_masked_config()["api_key"] == "***"

    def test_str返回name(self):
        assert str(MemorySpace(name="记忆空间A")) == "记忆空间A"
