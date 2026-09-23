"""core.utils.loader.LanguageLoader 纯单元测试。

规格：按 (app, lang) 缓存 yaml 翻译，提供点号路径取值与深度合并。
- get: 点号路径递归取值，缺失/中间非 dict 返回默认；
- _deep_merge: 嵌套字典合并，override 覆盖，非 dict 直接替换；
- clear_language_cache: 按 app/lang 维度清缓存。
不依赖 DB；用不存在的 app 得到空翻译，再直接注入 translations 验证取值逻辑。
"""

import pytest

from apps.core.utils.loader import LanguageLoader, clear_language_cache, normalize_language

pytestmark = pytest.mark.unit


@pytest.fixture
def loader():
    lo = LanguageLoader(app="__no_such_app__", default_lang="en")
    lo.translations = {
        "os": {"linux": "Linux", "win": "Windows"},
        "cloud_region": {"default": {"name": "默认区域"}},
        "flat": "value",
    }
    return lo


class TestGet:
    def test_单层取值(self, loader):
        assert loader.get("flat") == "value"

    def test_多层点号路径(self, loader):
        assert loader.get("os.linux") == "Linux"
        assert loader.get("cloud_region.default.name") == "默认区域"

    def test_缺失键返回默认(self, loader):
        assert loader.get("os.macos") is None
        assert loader.get("os.macos", "fallback") == "fallback"

    def test_中间非字典返回默认(self, loader):
        # flat 是字符串，再下钻应回退默认
        assert loader.get("flat.sub", "d") == "d"


class TestDeepMerge:
    def test_嵌套合并override覆盖(self, loader):
        base = {"a": {"x": 1, "y": 2}, "b": 1}
        override = {"a": {"y": 9, "z": 3}, "c": 4}
        merged = loader._deep_merge(base, override)
        assert merged == {"a": {"x": 1, "y": 9, "z": 3}, "b": 1, "c": 4}
        # 不改原 base
        assert base == {"a": {"x": 1, "y": 2}, "b": 1}

    def test_非字典直接替换(self, loader):
        assert loader._deep_merge({"a": {"x": 1}}, {"a": "str"}) == {"a": "str"}


class TestEmptyAppFallback:
    def test_不存在的app翻译为空(self):
        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        assert lo.get("anything", "d") == "d"


class TestNormalizeLanguage:
    def test_zh_aliases_map_to_simplified_pack(self):
        for alias in ("zh", "zh-CN", "zh_CN", "zh-Hans"):
            assert normalize_language(alias) == "zh-Hans"

    def test_en_aliases_map_to_en(self):
        for alias in ("en", "en-US", "en_US"):
            assert normalize_language(alias) == "en"

    def test_unknown_locale_kept(self):
        assert normalize_language("zh-TW") == "zh-TW"
        assert normalize_language("ja") == "ja"

    def test_empty_and_none_fall_back_to_en(self):
        assert normalize_language(None) == "en"
        assert normalize_language("  ") == "en"

    def test_zh_cn_loads_core_simplified_pack(self):
        clear_language_cache(app="core")
        loader = LanguageLoader(app="core", default_lang="zh-CN")
        assert loader.default_lang == "zh-Hans"
        assert loader.get("error.no_permission_access_team") == "无权访问该团队数据"

    def test_en_us_loads_core_english_pack(self):
        loader = LanguageLoader(app="core", default_lang="en-US")
        assert loader.default_lang == "en"
        assert loader.get("error.no_permission_access_team") == "No permission to access this team"


class TestClearCache:
    def test_按app清缓存(self):
        LanguageLoader(app="__cache_app__", default_lang="en")
        from apps.core.utils import loader as loader_mod
        assert ("__cache_app__", "en") in loader_mod._translation_cache
        clear_language_cache(app="__cache_app__")
        assert ("__cache_app__", "en") not in loader_mod._translation_cache
