"""验证 _load_language_dir 不再跳过 legacy 单文件 <lang>.yaml 内容。

回归场景:Task 3 之前 apps/<app>/language/<lang>.yaml 包含全部翻译,
Task 5 才会拆为 core/<segment>.yaml。Task 3 的 _load_language_dir 把 <lang>.yaml
视为壳并跳过,导致过渡期内调用方读到空翻译,直到 Task 5 完成。
本测试锁定"legacy 单文件仍被读取"的兼容行为。
"""

import os

import pytest

from apps.core.utils.loader import LanguageLoader, clear_language_cache

pytestmark = pytest.mark.unit


class TestLoadLanguageDirLegacyCompat:
    def test_legacy_single_file_en_yaml_still_read(self, tmp_path, monkeypatch):
        """legacy 模式的 apps/<app>/language/en.yaml 应被读取。"""
        # 不建 core/ 子目录,只有 en.yaml(模拟未迁移的 app)
        (tmp_path / "en.yaml").write_text("os:\n  linux: Linux\n", encoding="utf-8")

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        lo.base_dir = str(tmp_path)
        result = lo._load_language_dir("en")

        assert result == {"os": {"linux": "Linux"}}, (
            f"legacy en.yaml 应被读取,实际 {result}"
        )

    def test_enterprise_legacy_single_file_still_read(self, tmp_path, monkeypatch):
        """legacy 模式的 enterprise/<lang>.yaml 应被读取。"""
        # enterprise 路径结构: apps/<app>/enterprise/language/<lang>.yaml
        enterprise_root = tmp_path / "apps" / "__legacy_ent__" / "enterprise" / "language"
        enterprise_root.mkdir(parents=True)
        (enterprise_root / "en.yaml").write_text("os:\n  mac: Mac\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        lo = LanguageLoader(app="__legacy_ent__", default_lang="en")
        result = lo._load_enterprise_language("en")
        assert result == {"os": {"mac": "Mac"}}, (
            f"legacy enterprise en.yaml 应被读取,实际 {result}"
        )

    def test_main_file_yaml_load_raises_returns_empty(self, tmp_path, monkeypatch):
        """回归原 test_small_utils_branches 测试 1:main yaml 解析失败 -> 空 dict(无 plugins)。"""
        base = tmp_path / "apps" / "__main_read_fail__" / "language"
        base.mkdir(parents=True)
        (base / "en.yaml").write_text("os:\n  linux: Linux\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        import apps.core.utils.loader as loader_mod

        monkeypatch.setattr(
            loader_mod.yaml, "safe_load",
            lambda *a, **k: (_ for _ in ()).throw(ValueError("bad yaml"))
        )

        clear_language_cache(app="__main_read_fail__")
        loader = LanguageLoader(app="__main_read_fail__", default_lang="en")
        # 主文件解析异常被吞;_load_plugin_language 返回空 wrapper,不应用层关注
        # 断言无用户可见 key 被加载(get 全部返回 None)
        assert loader.get("os.linux") is None, (
            f"主 yaml 失败后,os.linux 应为 None,实际 {loader.get('os.linux')!r}"
        )
        clear_language_cache(app="__main_read_fail__")

    def test_enterprise_file_read_raises_keeps_main(self, tmp_path, monkeypatch):
        """回归原 test_small_utils_branches 测试 2:enterprise 解析失败 -> 主文件保留。"""
        from apps.core.utils.loader import clear_language_cache

        # 主文件
        base = tmp_path / "apps" / "__ent_read_fail__" / "language"
        base.mkdir(parents=True)
        (base / "en.yaml").write_text("os:\n  linux: Linux\n", encoding="utf-8")
        # enterprise 文件
        ent = tmp_path / "apps" / "__ent_read_fail__" / "enterprise" / "language"
        ent.mkdir(parents=True)
        (ent / "en.yaml").write_text("os:\n  mac: Mac\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        import apps.core.utils.loader as loader_mod

        real_safe_load = loader_mod.yaml.safe_load
        calls = {"n": 0}

        def flaky_safe_load(stream, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:  # 主文件
                return real_safe_load(stream, *a, **k)
            raise ValueError("enterprise bad yaml")

        monkeypatch.setattr(loader_mod.yaml, "safe_load", flaky_safe_load)

        clear_language_cache(app="__ent_read_fail__")
        loader = LanguageLoader(app="__ent_read_fail__", default_lang="en")
        assert loader.get("os.linux") == "Linux"
        assert loader.get("os.mac", "fallback") == "fallback"
        clear_language_cache(app="__ent_read_fail__")


class TestFlowOnboardingUILoad:
    """验证 flow_onboarding_ui 从 monitor/language/{lang}.yaml 正确加载。"""

    def test_flow_onboarding_ui_从zhHans加载(self):
        """flow_onboarding_ui 从 zh-Hans.yaml 加载。"""
        clear_language_cache(app="monitor", lang="zh-Hans")
        loader = LanguageLoader(app="monitor", default_lang="zh-Hans")
        val = loader.get("flow_onboarding_ui.accessAsset")
        assert val == "接入资产", f"期望 '接入资产', 实际 {val!r}"
        clear_language_cache(app="monitor", lang="zh-Hans")

    def test_flow_onboarding_ui_从en加载(self):
        """flow_onboarding_ui 从 en.yaml 加载。"""
        clear_language_cache(app="monitor", lang="en")
        loader = LanguageLoader(app="monitor", default_lang="en")
        val = loader.get("flow_onboarding_ui.accessAsset")
        assert val == "Access Asset", f"期望 'Access Asset', 实际 {val!r}"
        clear_language_cache(app="monitor", lang="en")
