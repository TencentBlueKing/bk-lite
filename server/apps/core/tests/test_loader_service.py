import pydantic.root_model  # noqa

import pytest

from apps.core.utils import loader as loader_mod
from apps.core.utils.loader import (
    LanguageLoader,
    clear_language_cache,
    preload_language_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_language_cache()
    yield
    clear_language_cache()


class TestLanguageLoaderLoad:
    def test_loads_main_yaml(self, tmp_path, mocker):
        # 边界：os.path.exists + open。主文件命中，企业目录不命中。
        def fake_exists(path):
            return path == "apps/core/language/en.yaml"

        mocker.patch.object(loader_mod.os.path, "exists", side_effect=fake_exists)
        mocker.patch.object(
            loader_mod.yaml, "safe_load", return_value={"os": {"linux": "Linux"}}
        )
        m = mocker.patch("builtins.open", mocker.mock_open(read_data="ignored"))

        ld = LanguageLoader(app="core", default_lang="en")
        assert ld.get("os.linux") == "Linux"
        m.assert_called_once()

    def test_deep_merge_with_enterprise(self, mocker):
        def fake_exists(path):
            return True  # 主文件 + 企业文件都存在

        mocker.patch.object(loader_mod.os.path, "exists", side_effect=fake_exists)
        mocker.patch.object(
            loader_mod.yaml,
            "safe_load",
            side_effect=[
                {"a": {"x": 1}, "b": 2},  # 主文件
                {"a": {"y": 9}, "c": 3},  # 企业文件覆盖/合并
            ],
        )
        mocker.patch("builtins.open", mocker.mock_open(read_data="ignored"))

        ld = LanguageLoader(app="core", default_lang="en")
        assert ld.get("a.x") == 1
        assert ld.get("a.y") == 9
        assert ld.get("c") == 3

    def test_missing_files_returns_empty(self, mocker):
        mocker.patch.object(loader_mod.os.path, "exists", return_value=False)
        ld = LanguageLoader(app="core", default_lang="en")
        assert ld.translations == {}
        assert ld.get("anything", "DEF") == "DEF"

    def test_load_failure_logged_not_raised(self, mocker):
        mocker.patch.object(loader_mod.os.path, "exists", side_effect=lambda p: p == "apps/core/language/en.yaml")
        mocker.patch("builtins.open", side_effect=OSError("disk error"))
        ld = LanguageLoader(app="core", default_lang="en")
        assert ld.translations == {}


class TestLanguageLoaderGet:
    def _loader_with(self, mocker, data):
        mocker.patch.object(loader_mod.os.path, "exists", return_value=False)
        ld = LanguageLoader(app="core", default_lang="en")
        ld.translations = data
        return ld

    def test_nested_path(self, mocker):
        ld = self._loader_with(mocker, {"cloud_region": {"default": {"name": "Default"}}})
        assert ld.get("cloud_region.default.name") == "Default"

    def test_missing_returns_default(self, mocker):
        ld = self._loader_with(mocker, {"a": {"b": "v"}})
        assert ld.get("a.missing", "fallback") == "fallback"

    def test_path_into_nondict_returns_default(self, mocker):
        ld = self._loader_with(mocker, {"a": "scalar"})
        assert ld.get("a.b.c", "def") == "def"


class TestCache:
    def test_cache_hit_skips_reload(self, mocker):
        mocker.patch.object(loader_mod.os.path, "exists", return_value=False)
        load_spy = mocker.spy(LanguageLoader, "_load_language_file")
        LanguageLoader(app="core", default_lang="en")
        first = load_spy.call_count
        LanguageLoader(app="core", default_lang="en")
        assert load_spy.call_count == first  # 第二次走缓存，不再加载

    def test_clear_specific_app_lang(self):
        loader_mod._translation_cache[("a", "en")] = {"k": 1}
        loader_mod._translation_cache[("a", "zh-Hans")] = {"k": 2}
        loader_mod._translation_cache[("b", "en")] = {"k": 3}
        clear_language_cache(app="a", lang="en")
        assert ("a", "en") not in loader_mod._translation_cache
        assert ("a", "zh-Hans") in loader_mod._translation_cache
        assert ("b", "en") in loader_mod._translation_cache

    def test_clear_all(self):
        loader_mod._translation_cache[("a", "en")] = {"k": 1}
        clear_language_cache()
        assert loader_mod._translation_cache == {}

    def test_load_language_compat_method(self, mocker):
        mocker.patch.object(loader_mod.os.path, "exists", return_value=False)
        ld = LanguageLoader(app="core", default_lang="en")
        loader_mod._translation_cache[("core", "zh-Hans")] = {"hi": "你好"}
        ld.load_language("zh-Hans")
        assert ld.get("hi") == "你好"


class TestPreload:
    def test_preload_loaded_skipped_failed(self, mocker):
        # app1/en -> 有翻译(loaded); app1/zh -> 空(skipped); app2/en -> 异常(failed)
        def fake_init(self, app, default_lang="en"):
            self.app = app
            if app == "app2":
                raise RuntimeError("boom")
            self.translations = {"k": "v"} if default_lang == "en" else {}

        mocker.patch.object(LanguageLoader, "__init__", fake_init)
        result = preload_language_cache(apps=["app1", "app2"], languages=["en", "zh-Hans"])

        assert "app1/en" in result["loaded"]
        assert "app1/zh-Hans" in result["skipped"]
        assert "app2/en" in result["failed"]
        assert "app2/zh-Hans" in result["failed"]

    def test_preload_skips_already_cached(self, mocker):
        loader_mod._translation_cache[("app1", "en")] = {"k": "v"}
        init = mocker.patch.object(LanguageLoader, "__init__", return_value=None)
        result = preload_language_cache(apps=["app1"], languages=["en"])
        assert result["skipped"] == ["app1/en"]
        init.assert_not_called()
