"""cleanup_orphan_snapshot_objects 管理命令单元测试。

命令扫描 MinIO 中遗留的孤儿快照对象，支持 dry-run 与实际删除。
仅 mock 真实外部边界（MinIO storage.client.list_objects/storage.delete、
DB 实时路径查询 _fetch_live_paths）。断言扫描统计、孤儿识别、删除副作用、
prefix 匹配、样本截断、dry-run 不删除。
"""

from types import SimpleNamespace

import pytest

from apps.core.management.commands.cleanup_orphan_snapshot_objects import Command

pytestmark = pytest.mark.unit


def _obj(name, size):
    return SimpleNamespace(object_name=name, size=size)


def _make_config(mocker, objects):
    """构造一个带 mock storage 的 config 与底层 storage。"""
    storage = mocker.MagicMock()
    storage.bucket = "snap-bucket"
    storage.client.list_objects.return_value = iter(objects)
    field = mocker.MagicMock()
    field.storage = storage
    model = mocker.MagicMock()
    model.__name__ = "MonitorAlertMetricSnapshot"
    model._meta.get_field.return_value = field
    config = {"label": "monitor snapshot", "model": model, "field_name": "snapshots"}
    return config, storage


class TestMatchesPrefix:
    def test_basename_prefix_match(self):
        assert Command._matches_prefix("2025/06/monitoralertmetricsnapshot_1_ab.json.gz", "monitoralertmetricsnapshot_") is True

    def test_no_match(self):
        assert Command._matches_prefix("2025/06/other_1.json.gz", "monitoralertmetricsnapshot_") is False

    def test_no_slash_path(self):
        assert Command._matches_prefix("monitoralertmetricsnapshot_x", "monitoralertmetricsnapshot_") is True


class TestScanTarget:
    def test_identifies_orphans_dry_run(self, mocker):
        prefix = "monitoralertmetricsnapshot_"
        live = f"2025/{prefix}live.json.gz"
        orphan = f"2025/{prefix}orphan.json.gz"
        unrelated = "2025/otherfile.json.gz"
        config, storage = _make_config(mocker, [_obj(live, 100), _obj(orphan, 250), _obj(unrelated, 999)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", return_value={live})

        summary = cmd._scan_target(config, should_delete=False, sample_limit=10)

        assert summary["scanned_count"] == 2  # unrelated 被 prefix 过滤
        assert summary["orphan_count"] == 1
        assert summary["orphan_bytes"] == 250
        assert summary["deleted_count"] == 0
        assert summary["samples"] == [{"path": orphan, "size": 250}]
        storage.delete.assert_not_called()

    def test_deletes_when_flag_set(self, mocker):
        prefix = "monitoralertmetricsnapshot_"
        orphan = f"2025/{prefix}gone.json.gz"
        config, storage = _make_config(mocker, [_obj(orphan, 50)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", return_value=set())

        summary = cmd._scan_target(config, should_delete=True, sample_limit=10)

        assert summary["orphan_count"] == 1
        assert summary["deleted_count"] == 1
        storage.delete.assert_called_once_with(orphan)

    def test_sample_limit_truncates(self, mocker):
        prefix = "monitoralertmetricsnapshot_"
        objs = [_obj(f"2025/{prefix}o{i}.json.gz", 10) for i in range(5)]
        config, storage = _make_config(mocker, objs)

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", return_value=set())

        summary = cmd._scan_target(config, should_delete=False, sample_limit=2)
        assert summary["orphan_count"] == 5
        assert len(summary["samples"]) == 2


class TestHandle:
    def test_handle_all_targets_aggregates(self, mocker):
        cmd = Command()
        # patch _scan_target 返回固定 summary，验证 handle 聚合与 footer
        summary_a = {"label": "monitor snapshot", "bucket": "b", "prefix": "p", "live_count": 1, "scanned_count": 1, "orphan_count": 2, "orphan_bytes": 100, "deleted_count": 0, "samples": []}
        summary_b = {"label": "log snapshot", "bucket": "b", "prefix": "p", "live_count": 1, "scanned_count": 1, "orphan_count": 3, "orphan_bytes": 200, "deleted_count": 0, "samples": []}
        scan = mocker.patch.object(cmd, "_scan_target", side_effect=[summary_a, summary_b])
        writes = []
        cmd.stdout = SimpleNamespace(write=lambda m: writes.append(str(m)))
        cmd.style = SimpleNamespace(SUCCESS=lambda m: m)

        cmd.handle(target="all", delete=False, limit=20)

        assert scan.call_count == 2
        footer = writes[-1]
        assert "orphan_count=5" in footer
        assert "orphan_bytes=300" in footer
        assert "扫描" in footer

    def test_handle_single_target_delete_footer(self, mocker):
        cmd = Command()
        summary = {"label": "monitor snapshot", "bucket": "b", "prefix": "p", "live_count": 0, "scanned_count": 1, "orphan_count": 1, "orphan_bytes": 10, "deleted_count": 1, "samples": [{"path": "x", "size": 10}]}
        scan = mocker.patch.object(cmd, "_scan_target", return_value=summary)
        writes = []
        cmd.stdout = SimpleNamespace(write=lambda m: writes.append(str(m)))
        cmd.style = SimpleNamespace(SUCCESS=lambda m: m)

        cmd.handle(target="monitor", delete=True, limit=5)

        assert scan.call_count == 1
        assert "删除" in writes[-1]
        assert "deleted_count=1" in writes[-1]


class TestPrintSummary:
    def test_print_summary_includes_samples(self):
        cmd = Command()
        writes = []
        cmd.stdout = SimpleNamespace(write=lambda m: writes.append(str(m)))
        cmd.style = SimpleNamespace(SUCCESS=lambda m: m)
        summary = {"label": "log snapshot", "bucket": "lb", "prefix": "alertsnapshot_", "live_count": 2, "scanned_count": 3, "orphan_count": 1, "orphan_bytes": 42, "deleted_count": 0, "samples": [{"path": "p/x.gz", "size": 42}]}

        cmd._print_summary(summary, should_delete=False)

        assert any("DRY-RUN" in w for w in writes)
        assert any("sample orphan: p/x.gz (42 bytes)" in w for w in writes)
