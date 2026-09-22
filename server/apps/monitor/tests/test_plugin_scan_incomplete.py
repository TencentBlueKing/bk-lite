"""插件目录扫描不完整时不得当作完整 allowlist 做破坏性清理。"""

import json
from pathlib import Path

import pytest

from apps.monitor.management.services import plugin_migrate
from apps.monitor.management.utils import find_files_by_pattern
from apps.monitor.models import MonitorPlugin

pytestmark = pytest.mark.django_db


def test_find_files_raises_after_partial_directory_scan(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    plugin_a = root / "Telegraf" / "host_a"
    plugin_a.mkdir(parents=True)
    (plugin_a / "metrics.json").write_text('{"plugin":"Keep Me"}', encoding="utf-8")
    plugin_b = root / "Telegraf" / "host_b"
    plugin_b.mkdir()

    real_iterdir = Path.iterdir

    def wrapped(self):
        if self.resolve() == plugin_b.resolve():
            raise OSError("permission denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", wrapped)

    with pytest.raises(OSError, match="permission denied"):
        find_files_by_pattern(str(root), filename_pattern="metrics.json")


def test_complete_scan_returns_discovered_metrics_files(tmp_path):
    root = tmp_path / "plugins"
    plugin_a = root / "Telegraf" / "host_a"
    plugin_a.mkdir(parents=True)
    metrics = plugin_a / "metrics.json"
    metrics.write_text('{"plugin":"Keep Me"}', encoding="utf-8")

    found = find_files_by_pattern(str(root), filename_pattern="metrics.json")

    assert found == [str(metrics)]


def test_migrate_plugin_skips_cleanup_when_scan_incomplete(mocker):
    mocker.patch(
        "apps.monitor.management.services.plugin_migrate.find_files_by_pattern",
        side_effect=OSError("permission denied"),
    )
    cleanup = mocker.patch("apps.monitor.management.services.plugin_migrate._cleanup_removed_plugins")

    with pytest.raises(OSError, match="permission denied"):
        plugin_migrate.migrate_plugin()

    cleanup.assert_not_called()


def test_collect_ondisk_plugin_names_raises_on_unreadable_metrics(tmp_path):
    bad = tmp_path / "metrics.json"
    bad.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        plugin_migrate._collect_ondisk_builtin_plugin_names([str(bad)])


def test_complete_scan_still_deletes_missing_builtin_plugin(tmp_path):
    keep = MonitorPlugin.objects.create(name="Keep Plugin", is_pre=True)
    gone = MonitorPlugin.objects.create(name="Gone Plugin", is_pre=True)
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"plugin": "Keep Plugin"}), encoding="utf-8")

    plugin_migrate._cleanup_removed_plugins([str(metrics)])

    assert MonitorPlugin.objects.filter(id=keep.id).exists()
    assert not MonitorPlugin.objects.filter(id=gone.id).exists()
