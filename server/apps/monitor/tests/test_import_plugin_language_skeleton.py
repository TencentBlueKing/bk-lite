"""test_import_plugin_language_skeleton

验证 MonitorPluginService._ensure_language_skeleton 在 metrics.json 同目录自动创建
language/{en,zh-Hans}.yaml 空骨架;已有非空文件不覆盖。
"""

import pytest
import yaml

pytestmark = pytest.mark.unit


class TestEnsureLanguageSkeleton:
    def test_新建plugin自动生成language骨架(self, tmp_path):
        """metrics.json 同目录应自动生成 language/{en,zh-Hans}.yaml 空骨架。"""
        plugin_dir = tmp_path / "CollectorX" / "cat1" / "pluginX"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "metrics.json").write_text("{}", encoding="utf-8")

        from apps.monitor.services.plugin import MonitorPluginService
        MonitorPluginService._ensure_language_skeleton(plugin_dir, "Plugin-X")

        assert (plugin_dir / "language" / "en.yaml").is_file()
        assert (plugin_dir / "language" / "zh-Hans.yaml").is_file()

        en_data = yaml.safe_load((plugin_dir / "language" / "en.yaml").read_text(encoding="utf-8"))
        zh_data = yaml.safe_load((plugin_dir / "language" / "zh-Hans.yaml").read_text(encoding="utf-8"))
        assert en_data == {"Plugin-X": {"name": "", "desc": ""}}
        assert zh_data == {"Plugin-X": {"name": "", "desc": ""}}

    def test_已有language文件不覆盖(self, tmp_path):
        """language/ 已存在且非空,不应被覆盖。"""
        plugin_dir = tmp_path / "CollectorX" / "cat1" / "pluginX"
        plugin_dir.mkdir(parents=True)
        lang_dir = plugin_dir / "language"
        lang_dir.mkdir()
        (lang_dir / "en.yaml").write_text(
            "Plugin-X:\n  name: existing-en\n  desc: existing-desc\n",
            encoding="utf-8",
        )
        (lang_dir / "zh-Hans.yaml").write_text(
            "Plugin-X:\n  name: 已有翻译\n  desc: 已有描述\n",
            encoding="utf-8",
        )

        from apps.monitor.services.plugin import MonitorPluginService
        MonitorPluginService._ensure_language_skeleton(plugin_dir, "Plugin-X")

        en_data = yaml.safe_load((lang_dir / "en.yaml").read_text(encoding="utf-8"))
        zh_data = yaml.safe_load((lang_dir / "zh-Hans.yaml").read_text(encoding="utf-8"))
        assert en_data["Plugin-X"]["name"] == "existing-en"
        assert zh_data["Plugin-X"]["name"] == "已有翻译"

    def test_空文件被覆盖(self, tmp_path):
        """language/ 存在但 en.yaml 是空文件,应被覆盖为空骨架。"""
        plugin_dir = tmp_path / "CollectorX" / "cat1" / "pluginX"
        plugin_dir.mkdir(parents=True)
        lang_dir = plugin_dir / "language"
        lang_dir.mkdir()
        (lang_dir / "en.yaml").write_text("", encoding="utf-8")  # 空文件

        from apps.monitor.services.plugin import MonitorPluginService
        MonitorPluginService._ensure_language_skeleton(plugin_dir, "Plugin-X")

        en_data = yaml.safe_load((lang_dir / "en.yaml").read_text(encoding="utf-8"))
        assert en_data == {"Plugin-X": {"name": "", "desc": ""}}
