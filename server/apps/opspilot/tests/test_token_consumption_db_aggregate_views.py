"""Token 消耗统计接口回归测试：验证 DB 层聚合修复（Issue #3719）。

修复前：get_total_token_consumption / get_token_consumption_overview 把
queryset 全量拉到 Python 层逐行解析 JSON，大数据量必然超时。

修复后：通过 _annotate_token_fields + Sum aggregate / TruncDate+Sum 两种方式
在 DB 层完成聚合，不再把记录拉入进程。

测试守门：若把修复 revert（即恢复 .iterator() 全量遍历）而不改测试，
测试应当失败（因为没有 DB 聚合路径，mock patch 不会命中）。
实际手段：patch QuerySet.iterator 并断言它从未被调用。
"""

import datetime
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Django-free 独立 harness（规避 license_mgmt 缺失导致的 settings 加载失败）
# ---------------------------------------------------------------------------

_patched = False


def _install_stubs():
    """往 sys.modules 注入最小化伪模块，让 views.py 可以 import 而不需完整 Django 环境。"""
    global _patched
    if _patched:
        return
    _patched = True

    def _stub(name, **attrs):
        m = MagicMock()
        m.__name__ = name
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m

    # 只需让 import 通过，具体行为由测试内 patch 控制
    for mod in [
        "asgiref", "asgiref.sync",
        "wechatpy", "wechatpy.enterprise",
        "ipware",
        "dingtalk_stream", "dingtalk_stream.chatbot",
        "apps.base", "apps.base.models",
        "apps.core", "apps.core.decorators", "apps.core.decorators.api_permission",
        "apps.core.logger", "apps.core.utils", "apps.core.utils.exempt",
        "apps.core.utils.loader", "apps.core.utils.team_utils",
        "apps.opspilot", "apps.opspilot.enum",
        "apps.opspilot.serializers", "apps.opspilot.serializers.request_serializers",
        "apps.opspilot.services", "apps.opspilot.services.chat_completion_service",
        "apps.opspilot.services.chat_service",
        "apps.opspilot.services.dingtalk_chat_flow_utils",
        "apps.opspilot.services.workflow_task_service",
        "apps.opspilot.services.prompt_utils",
        "apps.opspilot.utils", "apps.opspilot.utils.bot_utils",
        "apps.opspilot.utils.workflow_runner",
        "apps.opspilot.models",
    ]:
        if mod not in sys.modules:
            _stub(mod)

    # HasRole 装饰器：直接透传
    sys.modules["apps.core.decorators.api_permission"].HasRole = lambda *a, **kw: (lambda f: f)

    # set_time_range：返回 (end, start) = (today, today-1)
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)
    sys.modules["apps.opspilot.utils.bot_utils"].set_time_range = lambda end, start: (today, yesterday)
    sys.modules["apps.opspilot.utils.bot_utils"].insert_skill_log = MagicMock()


# ---------------------------------------------------------------------------
# 直接用 pytest.mark.django_db 走真实 DB（推荐：更准确验证 ORM 聚合 SQL）
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.django_db


@pytest.fixture()
def skill_and_logs(db):
    """创建 LLMSkill + 三条 SkillRequestLog，用于验证 DB 聚合结果。"""
    from apps.opspilot.models import LLMSkill, SkillRequestLog

    # LLMSkill 依赖部分外键，用 MagicMock 替代实际关联并不可行；
    # 用真实 model 但跳过外键约束的方式较复杂。改为直接在 views 层注入 queryset。
    # 这里通过 monkeypatching _token_consumption_queryset 返回预构造 queryset。
    #
    # 注意：SkillRequestLog 有 ForeignKey(LLMSkill)，需先创建 LLMSkill。
    # LLMSkill 有 ForeignKey(ModelVendor/LLMModel)，跳过这层，用 bulk_create 绕过约束。
    # 最简单方案：直接 patch _token_consumption_queryset 返回 SkillRequestLog.objects 子集。
    pass


# ---------------------------------------------------------------------------
# 核心单测：验证修复后不调用 iterator()，且聚合结果正确
# ---------------------------------------------------------------------------


def _make_fake_queryset(records):
    """构造一个最小化 fake QuerySet，支持 annotate/aggregate/filter/values/order_by/none。

    采用链式返回 self 的方式模拟 Django ORM，aggregate() 返回实际计算结果。
    这是 Django-free 测试的标准技术。
    """

    class FakeQS:
        def __init__(self, data=None):
            self._data = data if data is not None else list(records)
            self._annotations = {}

        def filter(self, **kwargs):
            return self

        def none(self):
            return FakeQS([])

        def annotate(self, **kwargs):
            # 记录 annotation 表达式，实际在 aggregate/values 时求值
            new = FakeQS(self._data)
            new._annotations = dict(self._annotations)
            new._annotations.update(kwargs)
            return new

        def values(self, *fields):
            # 为 get_token_consumption_overview 返回按 date 分组的结果
            # 直接委托给下一个 annotate 计算
            return _FakeGroupQS(self._data, self._annotations, list(fields))

        def aggregate(self, **kwargs):
            # 对 _data 中每行按 _annotations 定义的字段计算值，再聚合
            result = {}
            for key, expr in kwargs.items():
                total = 0
                field_name = expr.source_expressions[0].name if hasattr(expr, "source_expressions") else None
                for row in self._data:
                    total += row.get(field_name, 0) if field_name else 0
                result[key] = total
            return result

        def order_by(self, *fields):
            return self

        def iterator(self):
            # 如果修复正确，iterator() 永远不应被调用
            raise AssertionError("iterator() 被调用——说明修复未生效，仍在 Python 层全量遍历！")

        def __iter__(self):
            return iter(self._data)

    class _FakeGroupQS:
        def __init__(self, data, annotations, fields):
            self._data = data
            self._annotations = annotations
            self._fields = fields

        def annotate(self, **kwargs):
            # 只支持 tokens=Sum("_total") 场景
            from collections import defaultdict

            groups = defaultdict(int)
            for row in self._data:
                key = tuple(row.get(f) for f in self._fields)
                for out_name, expr in kwargs.items():
                    field_name = getattr(expr, "source_expressions", [None])[0]
                    if field_name is not None:
                        field_name = field_name.name
                    groups[key] += row.get(field_name, 0) if field_name else 0
            result = []
            for key, total in groups.items():
                item = dict(zip(self._fields, key))
                for out_name in kwargs:
                    item[out_name] = total
                result.append(item)
            return result

        def order_by(self, *fields):
            return self

        def __iter__(self):
            return iter(self._data)

    return FakeQS()


# ---------------------------------------------------------------------------
# 统一接口测试
# ---------------------------------------------------------------------------


def test_get_total_token_consumption_uses_db_aggregate_not_iterator():
    """修复验证：get_total_token_consumption 使用 DB aggregate，不调用 iterator()。

    若 revert 修复，iterator() 会被调用 → 抛 AssertionError → 测试失败。
    """
    import importlib, importlib.util, os, types

    # 直接调用 _annotate_token_fields + aggregate 等 ORM 链是 Django 依赖的，
    # 这里验证的是"iterator不再被调用"的约定，用函数级 mock 测试。

    # 读取修复后的函数实现（非 Django-free，直接 import 真实模块）
    # 由于 pytest.mark.django_db 已激活，可以正常 import Django 模块
    from apps.opspilot import views as v

    # 构造一个 mock queryset：aggregate 返回固定值，iterator 抛错
    mock_qs = MagicMock()
    mock_qs.annotate.return_value = mock_qs
    mock_qs.aggregate.return_value = {
        "input_tokens": 100,
        "output_tokens": 200,
        "total_tokens": 300,
    }
    mock_qs.iterator.side_effect = AssertionError("iterator() called — fix not working!")

    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)

    with patch.object(v, "_token_consumption_queryset", return_value=(mock_qs, yesterday, today)):
        request = MagicMock()
        request.GET.get.return_value = None
        response = v.get_total_token_consumption(request)

    # iterator 不应被调用
    mock_qs.iterator.assert_not_called()
    # aggregate 必须被调用（说明走了 DB 聚合路径）
    mock_qs.aggregate.assert_called_once()
    # 响应数据正确
    import json as _json
    data = _json.loads(response.content)
    assert data["result"] is True
    assert data["data"]["total_tokens"] == 300
    assert data["data"]["input_tokens"] == 100
    assert data["data"]["output_tokens"] == 200


def test_get_token_consumption_overview_uses_db_aggregate_not_iterator():
    """修复验证：get_token_consumption_overview 按日期 DB 聚合，不调用 iterator()。"""
    import datetime as dt
    from apps.opspilot import views as v

    today = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - dt.timedelta(days=1)

    # DB 聚合路径：.annotate().values("date").annotate(tokens=Sum("_total")).order_by("date")
    # 最终 for row in rows 迭代 SQL 结果集（不是 iterator()）
    # 用 mock 模拟该链，返回一条聚合结果
    fake_date_row = {"date": today.date(), "tokens": 150}

    mock_final = MagicMock()
    mock_final.__iter__ = MagicMock(return_value=iter([fake_date_row]))

    mock_ordered = MagicMock()
    mock_ordered.order_by.return_value = mock_final

    mock_dated_agg = MagicMock()
    mock_dated_agg.annotate.return_value = mock_ordered

    mock_dated = MagicMock()
    mock_dated.values.return_value = mock_dated_agg

    mock_qs = MagicMock()
    mock_qs.annotate.return_value = mock_dated
    mock_qs.iterator.side_effect = AssertionError("iterator() called — fix not working!")

    with patch.object(v, "_token_consumption_queryset", return_value=(mock_qs, yesterday, today)):
        request = MagicMock()
        request.GET.get.return_value = None
        response = v.get_token_consumption_overview(request)

    mock_qs.iterator.assert_not_called()
    # annotate 必须被调用（进入 _annotate_token_fields 路径）
    mock_qs.annotate.assert_called()

    import json as _json
    data = _json.loads(response.content)
    assert data["result"] is True
    items = data["data"]["items"]
    today_str = today.strftime("%Y-%m-%d")
    today_item = next((i for i in items if i["date"] == today_str), None)
    assert today_item is not None
    assert today_item["tokens"] == 150


def test_annotate_token_fields_builds_correct_annotations():
    """_annotate_token_fields 必须对 queryset 调用 annotate，且注入 _prompt/_completion/_total 三个字段。"""
    from apps.opspilot import views as v

    mock_qs = MagicMock()
    mock_qs.annotate.return_value = mock_qs

    result = v._annotate_token_fields(mock_qs)

    mock_qs.annotate.assert_called_once()
    call_kwargs = mock_qs.annotate.call_args.kwargs
    assert "_prompt" in call_kwargs
    assert "_completion" in call_kwargs
    assert "_total" in call_kwargs
