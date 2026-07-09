# 本目录测试为 AST 静态分析，不依赖 Django；覆盖 server/conftest.py 的 autouse settings 夹具
import pytest


@pytest.fixture(autouse=True)
def use_dummy_cache_backend():
    """No-op override: 不需要 settings 夹具。"""


@pytest.fixture(autouse=True)
def disable_auth_middleware():
    """No-op override: 不需要 settings 夹具。"""