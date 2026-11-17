"""插件目录查找。storage 采集槽位对应 oceanstor 目录。"""

from pathlib import Path

from core.plugin.source_resolver import PluginSourceResolver

REPO_ROOT = Path(__file__).resolve().parents[3]
OSS_PLUGINS = REPO_ROOT / "agents/stargazer/plugins/inputs"
ENTERPRISE_ROOT = REPO_ROOT / "enterprise/agents/stargazer/enterprise"


def _resolver(oss_plugins, enterprise_root) -> PluginSourceResolver:
    return PluginSourceResolver(oss_plugins_base_dir=oss_plugins, enterprise_root=enterprise_root)


def test_storage_resolves_to_oceanstor_plugin_and_keeps_model_id():
    resolution = _resolver(OSS_PLUGINS, ENTERPRISE_ROOT).resolve("storage")

    assert resolution.model_id == "storage"
    assert resolution.source == "oss"
    assert resolution.plugin_path == OSS_PLUGINS / "oceanstor" / "plugin.yml"
    assert resolution.plugin_root == OSS_PLUGINS / "oceanstor"


def test_oceanstor_and_dell_unity_keep_their_own_directories():
    resolver = _resolver(OSS_PLUGINS, ENTERPRISE_ROOT)

    oceanstor = resolver.resolve("oceanstor")
    dell_unity = resolver.resolve("dell_unity")

    assert oceanstor.model_id == "oceanstor"
    assert oceanstor.plugin_path == OSS_PLUGINS / "oceanstor" / "plugin.yml"
    assert dell_unity.model_id == "dell_unity"
    assert dell_unity.plugin_path == OSS_PLUGINS / "dell_unity" / "plugin.yml"


def test_existing_storage_plugin_is_not_replaced_by_oceanstor(tmp_path):
    oss_plugins = tmp_path / "plugins" / "inputs"
    (oss_plugins / "storage").mkdir(parents=True)
    (oss_plugins / "oceanstor").mkdir()
    (oss_plugins / "storage" / "plugin.yml").write_text("name: storage\n", encoding="utf-8")
    (oss_plugins / "oceanstor" / "plugin.yml").write_text("name: oceanstor\n", encoding="utf-8")

    resolution = _resolver(oss_plugins, tmp_path / "enterprise").resolve("storage")

    assert resolution.model_id == "storage"
    assert resolution.plugin_path == oss_plugins / "storage" / "plugin.yml"


def test_storage_alias_uses_oceanstor_when_storage_directory_is_absent(tmp_path):
    oss_plugins = tmp_path / "plugins" / "inputs"
    (oss_plugins / "oceanstor").mkdir(parents=True)
    (oss_plugins / "oceanstor" / "plugin.yml").write_text("name: oceanstor\n", encoding="utf-8")

    resolution = _resolver(oss_plugins, tmp_path / "enterprise").resolve("storage")

    assert resolution.model_id == "storage"
    assert resolution.plugin_path == oss_plugins / "oceanstor" / "plugin.yml"
