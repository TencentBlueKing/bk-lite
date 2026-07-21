"""PluginGuideService / monitor_plugin guide API 测试。"""

from types import SimpleNamespace

from apps.monitor.services.plugin_guide import PluginGuideService


class TestPluginGuideServiceNormalizeLocale:
    def test_zh_variants(self):
        assert PluginGuideService.normalize_locale("zh-CN") == "zh-Hans"
        assert PluginGuideService.normalize_locale("zh_Hans") == "zh-Hans"
        assert PluginGuideService.normalize_locale("zh") == "zh-Hans"

    def test_en_variants(self):
        assert PluginGuideService.normalize_locale("en") == "en"
        assert PluginGuideService.normalize_locale("en-US") == "en"

    def test_default(self):
        assert PluginGuideService.normalize_locale(None) == "zh-Hans"
        assert PluginGuideService.normalize_locale("") == "zh-Hans"


class TestPluginGuideServiceResolveContent:
    def _make_plugin(self, **kwargs):
        defaults = dict(
            name="GuideDemo",
            collector="Telegraf",
            collect_type="database",
            description="demo",
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_reads_locale_guide_md(self, tmp_path, monkeypatch):
        root = tmp_path / "plugins"
        plugin_dir = root / "Telegraf" / "database" / "guidedemo"
        guide_dir = plugin_dir / "guide"
        guide_dir.mkdir(parents=True)
        (plugin_dir / "metrics.json").write_text(
            '{"plugin": "GuideDemo"}', encoding="utf-8"
        )
        (guide_dir / "zh-Hans.md").write_text("# 中文指引\n步骤一", encoding="utf-8")
        (guide_dir / "en.md").write_text("# English Guide\nStep 1", encoding="utf-8")

        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.DIRECTORY",
            str(root),
        )
        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.ENTERPRISE_DIRECTORY",
            str(tmp_path / "missing-ee"),
        )

        plugin = self._make_plugin()
        zh = PluginGuideService.get_guide(plugin, locale="zh-Hans")
        assert zh["has_guide"] is True
        assert zh["source"] == "guide/zh-Hans.md"
        assert "中文指引" in zh["content"]

        en = PluginGuideService.get_guide(plugin, locale="en")
        assert en["has_guide"] is True
        assert en["source"] == "guide/en.md"
        assert "English Guide" in en["content"]

    def test_falls_back_to_readme(self, tmp_path, monkeypatch):
        root = tmp_path / "plugins"
        plugin_dir = root / "Telegraf" / "database" / "guidedemo"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "metrics.json").write_text(
            '{"plugin": "GuideDemo"}', encoding="utf-8"
        )
        (plugin_dir / "README.md").write_text("# README 指引", encoding="utf-8")

        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.DIRECTORY",
            str(root),
        )
        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.ENTERPRISE_DIRECTORY",
            str(tmp_path / "missing-ee"),
        )

        plugin = self._make_plugin()
        data = PluginGuideService.get_guide(plugin, locale="zh-Hans")
        assert data["has_guide"] is True
        assert data["source"] == "README.md"
        assert "README 指引" in data["content"]

    def test_no_document(self, tmp_path, monkeypatch):
        root = tmp_path / "plugins"
        plugin_dir = root / "Telegraf" / "database" / "guidedemo"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "metrics.json").write_text(
            '{"plugin": "GuideDemo"}', encoding="utf-8"
        )

        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.DIRECTORY",
            str(root),
        )
        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.ENTERPRISE_DIRECTORY",
            str(tmp_path / "missing-ee"),
        )

        plugin = self._make_plugin()
        data = PluginGuideService.get_guide(plugin, locale="en")
        assert data == {
            "has_guide": False,
            "content": "",
            "locale": "en",
            "source": None,
            "name": "GuideDemo",
        }

    def test_resolves_real_elasticsearch_dir(self):
        plugin = self._make_plugin(
            name="ElasticSearch",
            collector="Telegraf",
            collect_type="database",
        )
        plugin_dir = PluginGuideService.resolve_plugin_dir(plugin)
        assert plugin_dir is not None
        assert plugin_dir.name == "elasticsearch"
        assert (plugin_dir / "metrics.json").is_file()
        guide = PluginGuideService.get_guide(plugin, locale="zh-Hans")
        assert guide["has_guide"] is True
        assert guide["source"] == "guide/zh-Hans.md"
        assert "ElasticSearch" in guide["content"]
        # name 取自 UI.json / metrics.json 的 object_name（应与目录/插件一致）
        assert guide["name"] == "ElasticSearch"

    def test_name_falls_back_to_plugin_name(self, tmp_path, monkeypatch):
        root = tmp_path / "plugins"
        plugin_dir = root / "Telegraf" / "database" / "guidedemo"
        guide_dir = plugin_dir / "guide"
        guide_dir.mkdir(parents=True)
        # metrics.json 不含 object_name，应回退到 plugin.name。
        (plugin_dir / "metrics.json").write_text(
            '{"plugin": "GuideDemo"}', encoding="utf-8"
        )
        (guide_dir / "zh-Hans.md").write_text("# Demo", encoding="utf-8")
        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.DIRECTORY",
            str(root),
        )
        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.ENTERPRISE_DIRECTORY",
            str(tmp_path / "missing-ee"),
        )
        plugin = self._make_plugin(name="GuideDemo")
        data = PluginGuideService.get_guide(plugin, locale="zh-Hans")
        assert data["name"] == "GuideDemo"

    def test_name_from_ui_json_overrides_metrics(self, tmp_path, monkeypatch):
        root = tmp_path / "plugins"
        plugin_dir = root / "Telegraf" / "database" / "guidedemo"
        guide_dir = plugin_dir / "guide"
        guide_dir.mkdir(parents=True)
        (plugin_dir / "metrics.json").write_text(
            '{"plugin": "GuideDemo"}', encoding="utf-8"
        )
        (plugin_dir / "UI.json").write_text(
            '{"object_name": "优雅监控对象"}', encoding="utf-8"
        )
        (guide_dir / "zh-Hans.md").write_text("# Demo", encoding="utf-8")
        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.DIRECTORY",
            str(root),
        )
        monkeypatch.setattr(
            "apps.monitor.services.plugin_guide.PluginConstants.ENTERPRISE_DIRECTORY",
            str(tmp_path / "missing-ee"),
        )
        plugin = self._make_plugin(name="GuideDemo")
        data = PluginGuideService.get_guide(plugin, locale="zh-Hans")
        assert data["name"] == "优雅监控对象"


class TestPluginGuideApiAction:
    def test_get_plugin_guide_returns_success_payload(self, mocker):
        from apps.core.utils.web_utils import WebUtils
        from apps.monitor.views.plugin import MonitorPluginViewSet

        plugin = SimpleNamespace(
            name="GuideApi",
            collector="Telegraf",
            collect_type="database",
        )
        request = SimpleNamespace(
            user=SimpleNamespace(locale="zh-Hans"),
            query_params={},
        )
        view = MonitorPluginViewSet()
        mocker.patch.object(view, "get_object", return_value=plugin)
        mocker.patch(
            "apps.monitor.views.plugin.PluginGuideService.get_guide",
            return_value={
                "has_guide": True,
                "content": "# API 指引",
                "locale": "zh-Hans",
                "source": "guide/zh-Hans.md",
                "name": "GuideApi",
            },
        )
        spy = mocker.spy(WebUtils, "response_success")

        resp = view.get_plugin_guide(request, pk=1)

        assert spy.call_count == 1
        payload = spy.call_args.args[0]
        assert payload["has_guide"] is True
        assert "API 指引" in payload["content"]
        assert payload["name"] == "GuideApi"
        assert resp is spy.spy_return

    def test_get_plugin_guide_without_document(self, mocker):
        from apps.core.utils.web_utils import WebUtils
        from apps.monitor.views.plugin import MonitorPluginViewSet

        plugin = SimpleNamespace(
            name="NoGuide",
            collector="Telegraf",
            collect_type="database",
        )
        request = SimpleNamespace(
            user=SimpleNamespace(locale="en"),
            query_params={},
        )
        view = MonitorPluginViewSet()
        mocker.patch.object(view, "get_object", return_value=plugin)
        mocker.patch(
            "apps.monitor.views.plugin.PluginGuideService.get_guide",
            return_value={
                "has_guide": False,
                "content": "",
                "locale": "en",
                "source": None,
                "name": "NoGuide",
            },
        )
        spy = mocker.spy(WebUtils, "response_success")

        view.get_plugin_guide(request, pk=1)

        payload = spy.call_args.args[0]
        assert payload["has_guide"] is False
        assert payload["content"] == ""
        assert payload["locale"] == "en"
        assert payload["source"] is None
        assert payload["name"] == "NoGuide"