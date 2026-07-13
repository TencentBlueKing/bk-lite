"""loader v3 多源加载单测。

覆盖:
- _load_language_dir: 扫 apps/<app>/language/ 下所有 *.yaml(只加载文件名匹配目标语言的文件,
  避免跨语言污染),多文件 deep-merge 等同单文件结果
- _load_plugin_language: 复用 find_files_by_pattern,扫每个 plugin 的 language/<lang>.yaml
- _load_language_file: base → plugins → enterprise 合并顺序
"""

import pytest

from apps.core.utils import loader as loader_mod
from apps.core.utils.loader import LanguageLoader, clear_language_cache

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_language_root(tmp_path, monkeypatch):
    """为 loader.app 指向不存在的应用,使用临时目录作为 base_dir 模拟。"""
    yield tmp_path


class TestLoadLanguageDir:
    def test_扫多个yaml合并(self, tmp_path, monkeypatch):
        """tmp_path 下放两个 yaml,验证 deep-merge。"""
        (tmp_path / "a.yaml").write_text("k1:\n  x: 1\n", encoding="utf-8")
        (tmp_path / "b.yaml").write_text("k1:\n  y: 2\nk2: v\n", encoding="utf-8")

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        lo.base_dir = str(tmp_path)
        result = lo._load_language_dir("en")

        assert result == {"k1": {"x": 1, "y": 2}, "k2": "v"}

    def test_legacy_en_yaml被读取_并与子文件deep_merge(self, tmp_path):
        """legacy <lang>.yaml 也是翻译内容之一,与子文件 deep-merge(不再视为壳)。"""
        (tmp_path / "en.yaml").write_text("core:\n  a: 1\nshared: legacy\n", encoding="utf-8")
        (tmp_path / "core.yaml").write_text("core:\n  b: 2\n", encoding="utf-8")

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        lo.base_dir = str(tmp_path)
        result = lo._load_language_dir("en")

        # legacy en.yaml 与 core.yaml 都参与合并
        assert result["core"] == {"a": 1, "b": 2}
        assert result["shared"] == "legacy"

    def test_目录不存在返回空(self, tmp_path):
        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        lo.base_dir = str(tmp_path / "nonexistent")
        assert lo._load_language_dir("en") == {}


class TestLoadPluginLanguage:
    def test_扫描plugin目录并加载language(self, tmp_path, monkeypatch):
        """构造两个 metrics.json,每个同目录有 language/en.yaml,验证加载。"""
        plugins_root = tmp_path / "plugins"
        (plugins_root / "CollectorA" / "cat1" / "pluginA").mkdir(parents=True)
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "metrics.json").write_text(
            '{"plugin": "Plugin-A"}', encoding="utf-8"
        )
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "language").mkdir()
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "language" / "en.yaml").write_text(
            "Plugin-A:\n  name: A Name\n  desc: A Desc\n", encoding="utf-8"
        )

        from apps.monitor.constants import plugin as plugin_constants
        monkeypatch.setattr(plugin_constants.PluginConstants, "DIRECTORY", str(plugins_root))
        monkeypatch.setattr(plugin_constants.PluginConstants, "ENTERPRISE_DIRECTORY", str(tmp_path / "no_enterprise"))

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        result = lo._load_plugin_language("en")

        assert result == {
            "monitor_object_plugin": {
                "Plugin-A": {"name": "A Name", "desc": "A Desc"}
            }
        }

    def test_缺失language文件不抛异常(self, tmp_path, monkeypatch):
        """plugin 有 metrics.json 但缺 language/en.yaml,应记录 warning 但不抛。"""
        plugins_root = tmp_path / "plugins"
        (plugins_root / "CollectorA" / "cat1" / "pluginA").mkdir(parents=True)
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "metrics.json").write_text(
            '{"plugin": "Plugin-A"}', encoding="utf-8"
        )
        # 不建 language/ 目录

        from apps.monitor.constants import plugin as plugin_constants
        monkeypatch.setattr(plugin_constants.PluginConstants, "DIRECTORY", str(plugins_root))
        monkeypatch.setattr(plugin_constants.PluginConstants, "ENTERPRISE_DIRECTORY", str(tmp_path / "no_enterprise"))

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        result = lo._load_plugin_language("en")
        assert result == {}

    def test_文件内key与plugin字段不一致报错但继续(self, tmp_path, monkeypatch, caplog):
        """language/en.yaml 顶层 key 与 metrics.json plugin 字段不一致:plugin 自身描述被丢,
        但 4 段翻译(monitor_object_metric 等)仍会被合并(因为合并是按整个 yaml 整体 deep_merge)。
        """
        plugins_root = tmp_path / "plugins"
        (plugins_root / "CollectorA" / "cat1" / "pluginA").mkdir(parents=True)
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "metrics.json").write_text(
            '{"plugin": "Plugin-A"}', encoding="utf-8"
        )
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "language").mkdir()
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "language" / "en.yaml").write_text(
            "Wrong-Key:\n  name: x\n", encoding="utf-8"
        )

        from apps.monitor.constants import plugin as plugin_constants
        monkeypatch.setattr(plugin_constants.PluginConstants, "DIRECTORY", str(plugins_root))
        monkeypatch.setattr(plugin_constants.PluginConstants, "ENTERPRISE_DIRECTORY", str(tmp_path / "no_enterprise"))

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        result = lo._load_plugin_language("en")
        # plugin 描述被丢(不在 monitor_object_plugin 下),但 yaml 内容被整体合并
        assert "monitor_object_plugin" not in result
        # 文件里只有 Wrong-Key 段,被原样合并
        assert result == {"Wrong-Key": {"name": "x"}}


class TestLoadLanguageFileMergeOrder:
    def test_合并顺序base_plugins_enterprise(self, tmp_path, monkeypatch):
        """base 设值,plugins 覆盖,enterprise 再覆盖。"""
        # base: 一个 yaml 含 monitor_object_plugin.<x>.name
        base = tmp_path / "base"
        base.mkdir()
        (base / "core.yaml").write_text(
            "monitor_object_plugin:\n  P:\n    name: from-base\n    desc: d-base\n", encoding="utf-8"
        )

        # plugins: 一个 plugin 目录
        plugins_root = tmp_path / "plugins"
        (plugins_root / "CollectorA" / "cat1" / "pluginA").mkdir(parents=True)
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "metrics.json").write_text(
            '{"plugin": "P"}', encoding="utf-8"
        )
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "language").mkdir()
        (plugins_root / "CollectorA" / "cat1" / "pluginA" / "language" / "en.yaml").write_text(
            "P:\n  name: from-plugins\n  desc: d-plugins\n", encoding="utf-8"
        )

        # enterprise: 同样覆盖 plugins 的 desc
        enterprise_root = tmp_path / "enterprise"
        (enterprise_root / "monitor" / "support-files" / "plugins" / "CollectorA" / "cat1" / "pluginA").mkdir(parents=True)
        (enterprise_root / "monitor" / "support-files" / "plugins" / "CollectorA" / "cat1" / "pluginA" / "metrics.json").write_text(
            '{"plugin": "P"}', encoding="utf-8"
        )
        (enterprise_root / "monitor" / "support-files" / "plugins" / "CollectorA" / "cat1" / "pluginA" / "language").mkdir()
        (enterprise_root / "monitor" / "support-files" / "plugins" / "CollectorA" / "cat1" / "pluginA" / "language" / "en.yaml").write_text(
            "P:\n  name: from-enterprise\n  desc: d-enterprise\n", encoding="utf-8"
        )

        from apps.monitor.constants import plugin as plugin_constants
        monkeypatch.setattr(plugin_constants.PluginConstants, "DIRECTORY", str(plugins_root))
        monkeypatch.setattr(plugin_constants.PluginConstants, "ENTERPRISE_DIRECTORY", str(enterprise_root / "monitor/support-files/plugins"))

        lo = LanguageLoader(app="monitor", default_lang="en")
        # base_dir 强制指向 tmp_path/base
        lo.base_dir = str(base)

        result = lo._load_language_file("en")
        assert result["monitor_object_plugin"]["P"]["name"] == "from-enterprise"
        assert result["monitor_object_plugin"]["P"]["desc"] == "d-enterprise"

    def test_缓存键不变(self):
        """验证 _get_cached_translations 仍用 (app, lang) 作为 key。"""
        clear_language_cache()
        LanguageLoader(app="__no_such__", default_lang="en")
        assert ("__no_such__", "en") in loader_mod._translation_cache
        clear_language_cache()

    def test_语言过滤_只匹配目标语言文件(self, tmp_path, monkeypatch):
        """_load_language_dir 只加载文件名匹配目标语言的 yaml,不跨语言污染。"""
        # en.yaml: 英文 flow_onboarding_ui
        (tmp_path / "en.yaml").write_text("flow_onboarding_ui:\n  a: A\n", encoding="utf-8")
        # zh-Hans.yaml: 中文 flow_onboarding_ui (不应混入 en)
        (tmp_path / "zh-Hans.yaml").write_text("flow_onboarding_ui:\n  a: 中文A\n", encoding="utf-8")
        # core/en.yaml: 英文
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "en.yaml").write_text("core_en: ok\n", encoding="utf-8")
        # core/zh-Hans.yaml: 中文 (不应混入 en)
        (tmp_path / "core" / "zh-Hans.yaml").write_text("core_zh: 中文\n", encoding="utf-8")

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        lo.base_dir = str(tmp_path)
        result = lo._load_language_dir("en")

        assert result.get("flow_onboarding_ui", {}).get("a") == "A", (
            f"英文应读 en.yaml, 实际 {result.get('flow_onboarding_ui')}"
        )
        assert result.get("flow_onboarding_ui", {}).get("a") != "中文A", "en 不应读到 zh-Hans.yaml"
        assert result.get("core_en") == "ok"
        assert "core_zh" not in result, "en 不应读到 core/zh-Hans.yaml"

    def test_语言过滤_无后缀子文件(self, tmp_path, monkeypatch):
        """无语言后缀的子目录文件(如 core/monitor_object.yaml 中文遗留)只被 zh-Hans 加载。"""
        # monitor_object.yaml 无语言后缀(中文遗留文件)
        (tmp_path / "monitor_object.yaml").write_text("monitor_object:\n  Host: 主机\n", encoding="utf-8")
        # monitor_object_en.yaml 有后缀(英文翻译)
        (tmp_path / "monitor_object_en.yaml").write_text("monitor_object:\n  Host: Host\n", encoding="utf-8")

        lo = LanguageLoader(app="__no_such_app__", default_lang="en")
        lo.base_dir = str(tmp_path)

        result_en = lo._load_language_dir("en")
        assert result_en.get("monitor_object", {}).get("Host") == "Host", (
            f"en 应读 monitor_object_en.yaml, 实际 {result_en.get('monitor_object', {}).get('Host')!r}"
        )

        lo.base_dir = str(tmp_path)
        lo2 = LanguageLoader(app="__no_such_app__", default_lang="zh-Hans")
        lo2.base_dir = str(tmp_path)
        result_zh = lo2._load_language_dir("zh-Hans")
        assert result_zh.get("monitor_object", {}).get("Host") == "主机", (
            f"zh-Hans 应读 monitor_object.yaml, 实际 {result_zh.get('monitor_object', {}).get('Host')!r}"
        )
