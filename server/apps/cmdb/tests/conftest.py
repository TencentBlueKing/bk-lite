"""CMDB 测试共享 fixtures：可配置的 FakeGraphClient，用于驱动 `with GraphClient() as ag:` 服务逻辑。"""

import pytest


class FakeGraphClient:
    """可配置的图客户端 fake，按方法名返回预置值并记录调用。

    用法：
        fake = FakeGraphClient(query_entity=([{...}], 1), create_entity={...})
        monkeypatch.setattr("apps.cmdb.services.model.GraphClient", lambda *a, **k: fake)
    """

    def __init__(self, **returns):
        self._returns = returns
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _resolve(self, name, default):
        value = self._returns.get(name, default)
        if callable(value):
            return value
        return value

    def __getattr__(self, name):
        if name.startswith("_") or name in ("calls",):
            raise AttributeError(name)

        def _method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            value = self._returns.get(name)
            if callable(value):
                return value(*args, **kwargs)
            if value is not None:
                return value
            # 合理默认：查询类返回 ([], 0)，其余返回 {}
            if name.startswith("query") or name in ("entity_objs", "full_text", "full_text_by_model"):
                return ([], 0)
            return {}

        return _method


@pytest.fixture
def fake_graph(monkeypatch):
    """返回一个工厂：在指定 service 模块打补丁注入 FakeGraphClient。"""

    def _install(module_path: str, **returns):
        fake = FakeGraphClient(**returns)
        monkeypatch.setattr(f"{module_path}.GraphClient", lambda *a, **k: fake)
        return fake

    return _install
