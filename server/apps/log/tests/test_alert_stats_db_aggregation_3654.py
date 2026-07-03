"""
Issue #3654: AlertViewSet.stats 全量物化告警记录到 Python list 后做 bucket 计算，无行数上界

验证修复：_get_step_based_stats 必须通过 DB 侧 GROUP BY 聚合（values+annotate+Count），
而不是 list(queryset.values_list(...)) 全量物化。

测试采用 Django-free 注入方式直接加载被测模块，绕过 ORM 及 settings 加载。

验证准则：revert 修复代码（将 values().annotate(cnt=Count("id")) 改回
list(queryset.values_list("created_at","level"))），所有 test_db_aggregation_*
测试必须失败——否则测试未覆盖修复点。
"""

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from textwrap import dedent
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Django-free 注入工具
# ---------------------------------------------------------------------------

def _install(name, **attrs):
    """往 sys.modules 注入一个伪模块（支持属性设置）。"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _ensure_django_db_models():
    """确保 django.db.models 可用（含 Min/Max/Count）。"""
    # django.db.models 通常可在无完整 settings 下导入
    import django.db.models as _m  # noqa
    from django.db.models import Count  # noqa
    return _m


# ---------------------------------------------------------------------------
# 伪 QuerySet：用于验证调用契约
# ---------------------------------------------------------------------------

class _AggregateQS:
    """
    模拟 Django QuerySet 最小接口，记录 values()/annotate()/order_by() 调用链。
    用于断言修复后代码确实走了 DB 侧聚合路径，而非 values_list() 全量物化路径。
    """

    def __init__(self, rows=None, min_time=None, max_time=None):
        # rows 格式：[{"created_at": dt, "level": "error", "cnt": 3}, ...]
        self._rows = rows or []
        self._min_time = min_time
        self._max_time = max_time
        self.values_list_called = False
        self.values_annotate_called = False

    def aggregate(self, **kwargs):
        return {"min_time": self._min_time, "max_time": self._max_time}

    def filter(self, **kwargs):
        return self

    def distinct(self):
        return self

    def count(self):
        return sum(r.get("cnt", 1) for r in self._rows)

    def values(self, *fields):
        """DB 侧聚合路径进入点。"""
        child = _AggregateChildQS(self._rows)
        child._parent = self
        self.values_annotate_called = True
        return child

    def values_list(self, *fields, flat=False):
        """全量物化路径（修复前）——记录调用以便测试断言。"""
        self.values_list_called = True
        # 返回旧格式 list（修复后不应被调用）
        return [(r["created_at"], r["level"]) for r in self._rows]

    def order_by(self, *fields):
        return self

    def __iter__(self):
        return iter(self._rows)


class _AggregateChildQS:
    """values() 之后的链式 QuerySet（支持 annotate/order_by）。"""

    def __init__(self, rows):
        self._rows = rows
        self._parent = None
        self.annotate_called = False
        self.annotate_kwargs = {}

    def annotate(self, **kwargs):
        self.annotate_called = True
        self.annotate_kwargs = kwargs
        return self

    def order_by(self, *fields):
        return self

    def filter(self, **kwargs):
        return self

    def __iter__(self):
        return iter(self._rows)

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, item):
        return self._rows[item]


# ---------------------------------------------------------------------------
# 直接测试 _get_step_based_stats 函数逻辑（无需加载完整 ViewSet）
# ---------------------------------------------------------------------------

def _load_get_step_based_stats():
    """
    从 policy.py 中提取 _get_step_based_stats 方法，使用独立 harness 包装。
    避免完整 ViewSet 初始化。
    """
    import os

    policy_path = os.path.join(
        os.path.dirname(__file__),
        "..", "views", "policy.py",
    )

    # 确保 django.db.models 可用
    import django.db.models as _models
    from django.db.models import Count, Min, Max

    # 读取并编译 policy.py 的 _get_step_based_stats 方法
    with open(policy_path, "r", encoding="utf-8") as f:
        source = f.read()

    # 提取方法体（从 def _get_step_based_stats 开始到下一个 @action 或 def 在同级缩进）
    lines = source.splitlines()
    start_line = None
    for i, line in enumerate(lines):
        if "def _get_step_based_stats(self, queryset, step_minutes):" in line:
            start_line = i
            break

    assert start_line is not None, "_get_step_based_stats not found in policy.py"

    # 收集方法的所有行（4 空格缩进块）
    method_lines = []
    for line in lines[start_line:]:
        if method_lines and (line.startswith("    @") or line.startswith("    def ")):
            break
        if method_lines and line and not line.startswith("    ") and not line.startswith("\t"):
            break
        method_lines.append(line)

    method_source = dedent("\n".join(method_lines))

    # 构建可执行的函数（去掉 self 参数，作为独立函数）
    func_source = "from datetime import datetime, timedelta, timezone\n"
    func_source += "from django.db import models\n"
    func_source += "from django.db.models import Count\n"
    func_source += "\n"
    func_source += method_source.replace(
        "def _get_step_based_stats(self, queryset, step_minutes):",
        "def _get_step_based_stats(queryset, step_minutes):"
    )

    ns = {}
    exec(compile(func_source, "<_get_step_based_stats>", "exec"), ns)
    return ns["_get_step_based_stats"]


# ---------------------------------------------------------------------------
# 测试：验证修复点 — DB 侧聚合路径
# ---------------------------------------------------------------------------

class TestAlertStatsDbAggregation:
    """
    修复验证：_get_step_based_stats 必须调用 values().annotate(cnt=Count("id"))，
    而不是 values_list() 全量物化。
    """

    def setup_method(self):
        self._fn = _load_get_step_based_stats()

    def _make_qs(self, rows, min_time, max_time):
        qs = _AggregateQS(rows=rows, min_time=min_time, max_time=max_time)
        return qs

    def test_db_aggregation_path_used_not_values_list(self):
        """
        核心修复验证：修复后代码走 values().annotate() 路径，
        而非 values_list() 全量物化。
        revert 修复后此测试必须失败。
        """
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            {"created_at": now, "level": "error", "cnt": 5},
            {"created_at": now + timedelta(minutes=30), "level": "warning", "cnt": 3},
        ]
        qs = self._make_qs(rows, min_time=now, max_time=now + timedelta(minutes=30))

        self._fn(qs, step_minutes=60)

        # 修复后：必须走 values+annotate 路径
        assert qs.values_annotate_called, (
            "修复后应调用 queryset.values().annotate()（DB 侧聚合），但未检测到调用。"
            "如果 revert 了修复，此断言将失败。"
        )
        # 修复后：不得全量物化
        assert not qs.values_list_called, (
            "修复后不应调用 queryset.values_list()（全量物化路径）。"
        )

    def test_bucket_counts_correct_with_aggregated_data(self):
        """
        bucket 统计结果：聚合行的 cnt 字段必须被正确汇总。
        修复前 cnt 字段不存在，bucket 计数将为 0 或出错。
        """
        now = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        # 两条聚合行落在同一个 bucket（1小时 step）
        rows = [
            {"created_at": now, "level": "error", "cnt": 10},
            {"created_at": now + timedelta(minutes=20), "level": "warning", "cnt": 4},
        ]
        qs = self._make_qs(rows, min_time=now, max_time=now + timedelta(minutes=20))

        result, time_range = self._fn(qs, step_minutes=60)

        assert len(result) >= 1
        first_bucket = result[0]
        # error 应有 10 条，warning 应有 4 条
        assert first_bucket["levels"].get("error", 0) == 10, (
            f"期望 error=10，实际 {first_bucket['levels']}。"
            "修复前没有 cnt 字段会导致计数错误。"
        )
        assert first_bucket["levels"].get("warning", 0) == 4, (
            f"期望 warning=4，实际 {first_bucket['levels']}。"
        )
        assert first_bucket["total"] == 14

    def test_empty_queryset_returns_empty(self):
        """空 queryset 返回空序列和 None 时间范围，行为不变。"""
        qs = _AggregateQS(rows=[], min_time=None, max_time=None)
        result, time_range = self._fn(qs, step_minutes=60)
        assert result == []
        assert time_range == {"start": None, "end": None}

    def test_multiple_buckets_separated_correctly(self):
        """
        多 bucket 场景：不同时间区间的告警归入正确的 bucket。
        """
        base = datetime(2025, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
        rows = [
            {"created_at": base, "level": "error", "cnt": 2},
            {"created_at": base + timedelta(hours=1, minutes=30), "level": "error", "cnt": 3},
        ]
        qs = self._make_qs(
            rows,
            min_time=base,
            max_time=base + timedelta(hours=1, minutes=30),
        )

        result, _ = self._fn(qs, step_minutes=60)

        assert len(result) >= 2, f"期望至少 2 个 bucket，实际 {len(result)}"
        # 第一个 bucket 含 error=2
        assert result[0]["levels"].get("error", 0) == 2
        # 第二个 bucket 含 error=3
        assert result[1]["levels"].get("error", 0) == 3

    def test_time_range_returned_correctly(self):
        """time_range 的 start/end 必须是 min_time/max_time 的 isoformat。"""
        now = datetime(2025, 5, 10, 0, 0, 0, tzinfo=timezone.utc)
        end = now + timedelta(hours=6)
        rows = [{"created_at": now, "level": "info", "cnt": 1}]
        qs = self._make_qs(rows, min_time=now, max_time=end)

        _, time_range = self._fn(qs, step_minutes=60)

        assert time_range["start"] == now.isoformat()
        assert time_range["end"] == end.isoformat()
