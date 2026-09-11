"""cleanup_orphan_snapshot_objects 管理命令单元测试。

命令扫描 MinIO 中遗留的孤儿快照对象，支持 dry-run 与实际删除。
仅 mock 真实外部边界（MinIO storage.client.list_objects/storage.delete、
DB 实时路径查询 _fetch_live_paths）。断言扫描统计、孤儿识别、删除副作用、
prefix 匹配、样本截断、dry-run 不删除、扫描窗口内新对象不被删。
"""

import inspect
import sys
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def settings():
    """Shadow pytest-django settings so root autouse fixtures不触发 Django setup。"""
    return types.SimpleNamespace(CACHES={}, MIDDLEWARE=())


def _ensure_pkg(name):
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(_ensure_pkg(parent), child, mod)
    return mod


def _stub_snapshot_models():
    """避免命令模块级导入 log/monitor model 时拉起未就绪的 CollectType。"""
    _ensure_pkg("apps.log.models")
    _ensure_pkg("apps.monitor.models")
    if "apps.log.models.policy" not in sys.modules:
        policy = types.ModuleType("apps.log.models.policy")
        policy.AlertSnapshot = type("AlertSnapshot", (), {"__name__": "AlertSnapshot"})
        sys.modules["apps.log.models.policy"] = policy
        sys.modules["apps.log.models"].policy = policy
    if "apps.monitor.models.monitor_policy" not in sys.modules:
        monitor_policy = types.ModuleType("apps.monitor.models.monitor_policy")
        monitor_policy.MonitorAlertMetricSnapshot = type(
            "MonitorAlertMetricSnapshot", (), {"__name__": "MonitorAlertMetricSnapshot"}
        )
        sys.modules["apps.monitor.models.monitor_policy"] = monitor_policy
        sys.modules["apps.monitor.models"].monitor_policy = monitor_policy


_stub_snapshot_models()

from apps.core.management.commands.cleanup_orphan_snapshot_objects import Command  # noqa: E402


def _obj(name, size, last_modified=None):
    return SimpleNamespace(object_name=name, size=size, last_modified=last_modified)


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

    def test_recheck_live_paths_keeps_committed_in_window_object(self, mocker):
        """第一次引用集合不含 P1，删除前第二次已含 P1，不得删除。"""
        prefix = "monitoralertmetricsnapshot_"
        p0 = f"2025/{prefix}p0.json.gz"
        p1 = f"2025/{prefix}p1.json.gz"
        old_lm = datetime(2020, 1, 1, tzinfo=timezone.utc)
        config, storage = _make_config(mocker, [_obj(p0, 10, old_lm), _obj(p1, 20, old_lm)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", side_effect=[{p0}, {p0, p1}])

        summary = cmd._scan_target(config, should_delete=True, sample_limit=10)

        storage.delete.assert_not_called()
        assert summary["deleted_count"] == 0

    def test_last_modified_after_scan_start_is_not_deleted(self, mocker):
        """P1 的 last_modified 晚于扫描起点，即使第二次仍不含它也不得删除。"""
        prefix = "monitoralertmetricsnapshot_"
        p0 = f"2025/{prefix}p0.json.gz"
        p1 = f"2025/{prefix}p1.json.gz"
        future_lm = datetime.now(timezone.utc) + timedelta(hours=1)
        config, storage = _make_config(mocker, [_obj(p0, 10), _obj(p1, 20, future_lm)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", side_effect=[{p0}, {p0}])

        summary = cmd._scan_target(config, should_delete=True, sample_limit=10)

        storage.delete.assert_not_called()
        assert summary["deleted_count"] == 0
        assert summary["orphan_count"] == 0

    def test_naive_last_modified_after_scan_start_is_not_deleted(self, mocker):
        """缺时区的 last_modified 晚于扫描起点时也不得当孤儿删。"""
        prefix = "monitoralertmetricsnapshot_"
        p1 = f"2025/{prefix}p1.json.gz"
        naive_future = datetime.now() + timedelta(hours=1)
        config, storage = _make_config(mocker, [_obj(p1, 20, naive_future)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", return_value=set())

        summary = cmd._scan_target(config, should_delete=True, sample_limit=10)

        storage.delete.assert_not_called()
        assert summary["deleted_count"] == 0

    def test_old_orphan_still_deleted_after_recheck(self, mocker):
        """last_modified 早于扫描起点且两次引用集合都不含它时，--delete 仍删除。"""
        prefix = "monitoralertmetricsnapshot_"
        orphan = f"2025/{prefix}gone.json.gz"
        old_lm = datetime(2020, 1, 1, tzinfo=timezone.utc)
        config, storage = _make_config(mocker, [_obj(orphan, 50, old_lm)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", side_effect=[set(), set()])

        summary = cmd._scan_target(config, should_delete=True, sample_limit=10)

        assert summary["orphan_count"] == 1
        assert summary["deleted_count"] == 1
        storage.delete.assert_called_once_with(orphan)

    def test_missing_last_modified_is_not_treated_as_new(self, mocker):
        """缺 last_modified 的旧对象在两次集合都不含它时仍可删。"""
        prefix = "monitoralertmetricsnapshot_"
        orphan = f"2025/{prefix}gone.json.gz"
        config, storage = _make_config(mocker, [_obj(orphan, 50)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", side_effect=[set(), set()])

        summary = cmd._scan_target(config, should_delete=True, sample_limit=10)

        storage.delete.assert_called_once_with(orphan)
        assert summary["deleted_count"] == 1

    def test_dry_run_does_not_delete_old_orphans(self, mocker):
        prefix = "monitoralertmetricsnapshot_"
        orphan = f"2025/{prefix}gone.json.gz"
        old_lm = datetime(2020, 1, 1, tzinfo=timezone.utc)
        config, storage = _make_config(mocker, [_obj(orphan, 50, old_lm)])

        cmd = Command()
        mocker.patch.object(cmd, "_fetch_live_paths", return_value=set())

        summary = cmd._scan_target(config, should_delete=False, sample_limit=10)

        assert summary["orphan_count"] == 1
        assert summary["deleted_count"] == 0
        storage.delete.assert_not_called()


class TestFetchLivePaths:
    def test_source_uses_orm_not_cursor_execute(self):
        source = inspect.getsource(Command._fetch_live_paths)
        assert "cursor.execute" not in source
        assert "RawSQL" not in source
        assert "connections[" not in source
        assert "values_list" in source

    def test_collects_nonempty_strings_via_values_list(self, mocker):
        model = mocker.MagicMock()
        field = mocker.MagicMock()
        field.attname = "snapshots"
        qs = model.objects.using.return_value
        qs.values_list.return_value = ["path/a.json.gz", "", None, "path/b.json.gz"]

        result = Command()._fetch_live_paths(model, field, "default")

        model.objects.using.assert_called_once_with("default")
        qs.values_list.assert_called_once_with("snapshots", flat=True)
        assert result == {"path/a.json.gz", "path/b.json.gz"}


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
