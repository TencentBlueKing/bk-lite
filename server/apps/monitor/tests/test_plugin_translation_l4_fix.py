"""L4 修复回归测试。

L4 bug: monitor/language/{en,zh-Hans}.yaml 的 monitor_object_plugin 段使用 display_name
作 key,而 _serialize_plugin 调用方用 plugin.name(内部 ID)查,实际命中率极低。

修复:plugin 翻译下沉到各 plugin 目录的 language/<lang>.yaml,key 改为 plugin.name。
本测试验证修复后 50+ 个抽样 plugin 的 lan.get() 返回非空翻译。
"""

import random

import pytest

from apps.core.utils.loader import LanguageLoader, clear_language_cache

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def en_loader():
    clear_language_cache()
    lo = LanguageLoader(app="monitor", default_lang="en")
    yield lo
    clear_language_cache()


@pytest.fixture(scope="module")
def zh_loader():
    clear_language_cache()
    lo = LanguageLoader(app="monitor", default_lang="zh-Hans")
    yield lo
    clear_language_cache()


class TestL4Fix:
    def test_en_loader含plugin翻译(self, en_loader):
        """抽样 50 个 plugin.name,断言 en 翻译命中。"""
        plugins = en_loader.get("monitor_object_plugin") or {}
        assert isinstance(plugins, dict)
        assert len(plugins) >= 250, f"应至少有 250 个 plugin 翻译,实际 {len(plugins)}"
        sample = random.sample(list(plugins.keys()), min(50, len(plugins)))
        for plugin_name in sample:
            entry = plugins[plugin_name]
            assert isinstance(entry, dict), f"{plugin_name} 翻译格式错"
            assert entry.get("name"), f"{plugin_name} 缺 name 翻译"
            assert entry.get("desc"), f"{plugin_name} 缺 desc 翻译"

    def test_zh_loader含plugin翻译(self, zh_loader):
        """抽样 50 个 plugin.name,断言 zh-Hans 翻译命中。"""
        plugins = zh_loader.get("monitor_object_plugin") or {}
        assert len(plugins) >= 250
        sample = random.sample(list(plugins.keys()), min(50, len(plugins)))
        for plugin_name in sample:
            entry = plugins[plugin_name]
            assert entry.get("name"), f"{plugin_name} 缺中文 name 翻译"
            assert entry.get("desc"), f"{plugin_name} 缺中文 desc 翻译"

    def test_5个B组plugin都有翻译(self, zh_loader):
        """Etcd/InfluxDB/Kafka-Exporter/Oracle-Exporter/Windows WMI 都有翻译。"""
        for p in ("Etcd", "InfluxDB", "Kafka-Exporter", "Oracle-Exporter", "Windows WMI"):
            entry = zh_loader.get(f"monitor_object_plugin.{p}")
            assert entry is not None, f"{p} 翻译缺失"
            assert entry.get("name"), f"{p} 缺 name"

    def test_windows_wmi展示名说明采集方式(self, zh_loader, en_loader):
        """WMI 与本机 Telegraf 采集必须在展示指标配置中可区分。"""
        assert zh_loader.get("monitor_object_plugin.Windows WMI.name") == "Windows 主机采集（WMI / Telegraf）"
        assert en_loader.get("monitor_object_plugin.Windows WMI.name") == "Windows Host Collection (WMI / Telegraf)"
