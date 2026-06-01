"""端到端流水线测试公共 fixture。

复用上层 apps/cmdb/tests/conftest.py 的 fake_graph fixture（pytest 自动继承）。
"""
import json
from pathlib import Path
from typing import Any

import pytest

E2E_ROOT = Path(__file__).parent


# --------------------------------------------------------------------------
# fixture 装载工具
# --------------------------------------------------------------------------


def _load(rel_path: str) -> Any:
    """从 fixtures/ 或 schemas/ 读 JSON。"""
    with open(E2E_ROOT / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def load_fixture():
    """test 里写 load_fixture('host/01_shell_output.json')。"""

    def _impl(rel_path: str):
        return _load(f"fixtures/{rel_path}")

    return _impl


@pytest.fixture
def load_schema():
    """test 里写 load_schema('host/01_shell_output.schema.json')。"""

    def _impl(rel_path: str):
        return _load(f"schemas/{rel_path}")

    return _impl


# --------------------------------------------------------------------------
# in-memory NATS 替身（配置文件采集那条路用；host 类不走 NATS 订阅）
# --------------------------------------------------------------------------


class FakeNatsClient:
    """
    模拟 server 端的 nats_client：
    - publish(subject, data) → 同步派发到本进程内已 register 的 handler
    - register(fn) → 收集 handler

    用法：
        from apps.cmdb.nats import nats as cmdb_nats
        fake = FakeNatsClient()
        fake.register_handlers_from_module(cmdb_nats)
        result = fake.publish("receive_config_file_result", payload)
    """

    def __init__(self):
        self.handlers: dict = {}
        self.published: list = []

    def register_handlers_from_module(self, module):
        for name in dir(module):
            fn = getattr(module, name)
            if callable(fn) and getattr(fn, "_nats_registered", False):
                self.handlers[name] = fn

    def publish(self, subject: str, data: Any):
        self.published.append((subject, data))
        fn = self.handlers.get(subject)
        if fn is None:
            return None
        return fn(data)


@pytest.fixture
def fake_nats():
    return FakeNatsClient()
