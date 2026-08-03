"""localize_ui_template 单测。

验证:
- 中文 locale(zh-Hans) → 保留 label
- 英文 locale(en) + label_en 非空 → 用 label_en 替换 label
- 英文 locale + label_en 为空 → 保留中文 label(降级)
- 非 form_fields/table_columns 内的 label 字段不受影响
"""

import json

import pytest

pytestmark = pytest.mark.unit


class TestLocalizeUiTemplate:
    def test_中文_locale_保留label(self):
        from apps.monitor.services.ui_template_locale import localize_ui_template

        content = {
            "form_fields": [
                {"name": "ENV_USER", "label": "用户名", "label_en": "Username"}
            ]
        }
        out = localize_ui_template(content, "zh-Hans")
        assert out["form_fields"][0]["label"] == "用户名"

    def test_英文_locale_使用_label_en(self):
        from apps.monitor.services.ui_template_locale import localize_ui_template

        content = {
            "form_fields": [
                {"name": "ENV_USER", "label": "用户名", "label_en": "Username"}
            ],
            "table_columns": [
                {"name": "node_ids", "label": "节点", "label_en": "Node"}
            ],
        }
        out = localize_ui_template(content, "en")
        assert out["form_fields"][0]["label"] == "Username"
        assert out["table_columns"][0]["label"] == "Node"

    def test_英文_locale_label_en为空时降级中文(self):
        from apps.monitor.services.ui_template_locale import localize_ui_template

        content = {
            "form_fields": [
                {"name": "X", "label": "中文标签", "label_en": ""}
            ]
        }
        out = localize_ui_template(content, "en")
        assert out["form_fields"][0]["label"] == "中文标签"

    def test_英文_locale_label_en为None时降级中文(self):
        from apps.monitor.services.ui_template_locale import localize_ui_template

        content = {
            "form_fields": [
                {"name": "X", "label": "中文", "label_en": None}
            ]
        }
        out = localize_ui_template(content, "en")
        assert out["form_fields"][0]["label"] == "中文"

    def test_非字段label不受影响(self):
        """label 字段在 widget_props.placeholder 等位置不应被替换。"""
        from apps.monitor.services.ui_template_locale import localize_ui_template

        content = {
            "form_fields": [
                {
                    "name": "X",
                    "label": "中文",  # 应被替换
                    "label_en": "English",
                    "widget_props": {
                        "placeholder": "中文 placeholder"  # 不应被替换
                    },
                }
            ]
        }
        out = localize_ui_template(content, "en")
        assert out["form_fields"][0]["label"] == "English"
        assert out["form_fields"][0]["widget_props"]["placeholder"] == "中文 placeholder"

    def test_空dict直接返回(self):
        from apps.monitor.services.ui_template_locale import localize_ui_template

        assert localize_ui_template({}, "en") == {}
        assert localize_ui_template(None, "en") is None  # type: ignore[arg-type]

    def test_深嵌套label被替换(self):
        from apps.monitor.services.ui_template_locale import localize_ui_template

        content = {
            "sections": [
                {
                    "title": {"label": "标题", "label_en": "Title"},
                    "fields": [
                        {"label": "子字段", "label_en": "Sub Field"}
                    ]
                }
            ]
        }
        out = localize_ui_template(content, "en")
        assert out["sections"][0]["title"]["label"] == "Title"
        assert out["sections"][0]["fields"][0]["label"] == "Sub Field"


class TestEnrichUiTemplateFromPluginFiles:
    def test_overlays_guide_short_and_section_from_disk(self, tmp_path, monkeypatch):
        from apps.monitor.services import ui_template_locale as locale_mod
        from apps.monitor.services.plugin_guide import PluginGuideService

        plugin_dir = tmp_path / "web"
        plugin_dir.mkdir()
        (plugin_dir / "UI.json").write_text(
            json.dumps(
                {
                    "form_fields": [
                        {
                            "name": "auth_type",
                            "guide_short": "认证方式悬浮说明",
                            "section": "auth",
                        },
                        {
                            "name": "response_timeout",
                            "guide_short": "超时悬浮说明",
                            "section": "response",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(PluginGuideService, "resolve_plugin_dir", staticmethod(lambda plugin: plugin_dir))

        content = {
            "form_fields": [
                {"name": "auth_type", "label": "认证方式"},
                {"name": "response_timeout", "label": "请求超时"},
                {"name": "interval", "label": "间隔", "guide_short": "旧说明"},
            ]
        }
        out = locale_mod.enrich_ui_template_from_plugin_files(content, plugin=object())
        fields = {item["name"]: item for item in out["form_fields"]}

        assert fields["auth_type"]["guide_short"] == "认证方式悬浮说明"
        assert fields["auth_type"]["section"] == "auth"
        assert fields["response_timeout"]["guide_short"] == "超时悬浮说明"
        assert fields["response_timeout"]["section"] == "response"
        # 磁盘未声明的字段保留原值
        assert fields["interval"]["guide_short"] == "旧说明"


class TestResolveSupportCollectDetect:
    def test_prefers_metrics_json_over_fallback(self, tmp_path, monkeypatch):
        from apps.monitor.services import ui_template_locale as locale_mod
        from apps.monitor.services.plugin_guide import PluginGuideService

        plugin_dir = tmp_path / "web"
        plugin_dir.mkdir()
        (plugin_dir / "metrics.json").write_text(
            json.dumps({"support_collect_detect": False}),
            encoding="utf-8",
        )
        monkeypatch.setattr(PluginGuideService, "resolve_plugin_dir", staticmethod(lambda plugin: plugin_dir))

        assert locale_mod.resolve_support_collect_detect(object(), fallback=True) is False

    def test_falls_back_when_metrics_missing(self, tmp_path, monkeypatch):
        from apps.monitor.services import ui_template_locale as locale_mod
        from apps.monitor.services.plugin_guide import PluginGuideService

        plugin_dir = tmp_path / "web"
        plugin_dir.mkdir()
        monkeypatch.setattr(PluginGuideService, "resolve_plugin_dir", staticmethod(lambda plugin: plugin_dir))

        assert locale_mod.resolve_support_collect_detect(object(), fallback=True) is True
        assert locale_mod.resolve_support_collect_detect(None, fallback=False) is False
