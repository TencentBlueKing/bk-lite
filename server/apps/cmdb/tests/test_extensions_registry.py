"""社区扩展注册表纯单测（IoC：社区定义槽位，谁注册由调用方决定）。"""

from apps.cmdb.extensions import registry


def test_get_returns_default_when_unregistered():
    assert registry.get("nonexistent_slot", "fallback") == "fallback"


def test_register_then_get():
    sentinel = object()
    registry.register("demo_slot", sentinel)
    assert registry.get("demo_slot") is sentinel


def test_register_overwrites():
    registry.register("demo_slot2", 1)
    registry.register("demo_slot2", 2)
    assert registry.get("demo_slot2") == 2
