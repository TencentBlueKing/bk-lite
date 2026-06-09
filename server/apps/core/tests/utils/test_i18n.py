"""core.utils.i18n.TranslateDict 纯单元测试。

规格：dict 子类，取值时经 django gettext 翻译。无激活翻译时 gettext 返回原文，
因此键存在则返回原值，get 缺失键返回默认值，items/values/copy 行为与翻译一致。
"""

import pytest

from apps.core.utils.i18n import TranslateDict

pytestmark = pytest.mark.unit


def test_getitem_无激活翻译时返回原文():
    d = TranslateDict({"greeting": "hello"})
    assert d["greeting"] == "hello"


def test_get_命中与缺失():
    d = TranslateDict({"a": "x"})
    assert d.get("a") == "x"
    assert d.get("missing") is None
    assert d.get("missing", "default") == "default"


def test_items_values_经翻译返回():
    d = TranslateDict({"a": "x", "b": "y"})
    assert dict(d.items()) == {"a": "x", "b": "y"}
    assert sorted(d.values()) == ["x", "y"]


def test_copy_仍为_translatedict():
    d = TranslateDict({"a": "x"})
    c = d.copy()
    assert isinstance(c, TranslateDict)
    assert c["a"] == "x"
