"""CMDB BDD：公共选项库（PublicEnumLibrary）业务规则（中文 Gherkin）。

对照 spec/prd/CMDB·模型管理·公共选项库：
- 建库/改库/删库的字段校验；
- options 变更触发模型属性快照同步；
- 删除前扫描所有模型的 enum 属性，发现引用则阻断删除并回传引用清单；
- 按团队列出选项库并以 editable 标记越权场景。

5 条 happy path + 7 条 corner case，全部走真实服务层与 ORM，仅在图查询/异步任务边界打桩。
"""

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.models.public_enum_library import PublicEnumLibrary
from apps.cmdb.services import public_enum_library as svc
from apps.core.exceptions.base_app_exception import BaseAppException

FEATURE = str(Path(__file__).parent / "public_enum_library.feature")
scenarios(FEATURE)

MODULE = "apps.cmdb.services.public_enum_library"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx():
    return {
        "result": None,
        "error": None,
        "list_result": None,
        "model_attrs": [],  # 模拟图库中的模型/属性
        "snapshot_calls": [],
        "library_id": None,  # 最近一次 create_library 写入的 library_id
    }


@pytest.fixture(autouse=True)
def _patch_parse(monkeypatch):
    """parse_attrs 默认走真实 JSON 解析即可。"""
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.parse_attrs",
        lambda raw: json.loads(raw) if isinstance(raw, str) else (raw or []),
    )


@pytest.fixture(autouse=True)
def _patch_graph(monkeypatch, ctx):
    """每个场景共享一份 fake GraphClient：query_entity(MODEL,...) 回放 ctx['model_attrs']。"""

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def query_entity(self, *args, **kwargs):
            return ctx["model_attrs"], len(ctx["model_attrs"])

    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *a, **k: _FakeClient())


@pytest.fixture(autouse=True)
def _patch_snapshot(monkeypatch, ctx):
    """拦截 celery 异步快照同步任务，记录调用次数。"""

    def _enqueue(library_id, trigger, operator):
        ctx["snapshot_calls"].append({"library_id": library_id, "trigger": trigger, "operator": operator})
        return "task-id"

    monkeypatch.setattr(f"{MODULE}.enqueue_library_snapshot_refresh", _enqueue)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_options(raw: str):
    return json.loads(raw)


def _parse_team(raw: str):
    """team 既可能是合法 JSON 数组，也可能是测试故意传入的非数组字符串。"""
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _create_library_record(library_id, name, team, options):
    return PublicEnumLibrary.objects.create(
        library_id=library_id,
        name=name,
        team=team,
        options=options,
        created_by="admin",
        updated_by="admin",
    )


# ---------------------------------------------------------------------------
# 背景
# ---------------------------------------------------------------------------

@given("公共选项库表已就绪")
def _table_ready(db):
    PublicEnumLibrary.objects.all().delete()


@given("模型库中没有任何模型属性引用现有选项库")
def _no_refs(ctx):
    ctx["model_attrs"] = []


# ---------------------------------------------------------------------------
# 假设 (Given): 预置数据
# ---------------------------------------------------------------------------

@given(parsers.re(
    r'已存在选项库 "(?P<library_id>[^"]+)" name="(?P<name>[^"]*)" team=(?P<team>\[[^\]]*\]) '
    r'options=(?P<options>\[.*\])$'
))
def _given_existing_library(db, library_id, name, team, options):
    _create_library_record(library_id, name, json.loads(team), _parse_options(options))


@given(parsers.parse(
    '模型 "{model_id}"（{model_name}）的属性 "{attr_id}"（{attr_name}）引用了 "{library_id}"'
))
def _given_model_attr_ref(ctx, model_id, model_name, attr_id, attr_name, library_id):
    ctx["model_attrs"] = [{
        "model_id": model_id,
        "model_name": model_name,
        "attrs": json.dumps([{
            "attr_id": attr_id,
            "attr_name": attr_name,
            "attr_type": "enum",
            "enum_rule_type": "public_library",
            "public_library_id": library_id,
        }]),
    }]


# ---------------------------------------------------------------------------
# 当 (When): 执行业务操作
# ---------------------------------------------------------------------------

def _run_create(ctx, operator, name, team, options, *, expect_error: bool):
    payload = {"name": name, "team": _parse_team(team), "options": _parse_options(options)}
    if expect_error:
        try:
            ctx["result"] = svc.create_library(payload, operator)
        except BaseAppException as exc:
            ctx["error"] = exc
    else:
        ctx["result"] = svc.create_library(payload, operator)
        ctx["library_id"] = ctx["result"]["library_id"]


@when(parsers.re(
    r'管理员 "(?P<operator>[^"]+)" 创建选项库 name="(?P<name>[^"]*)" team=(?P<team>[^ ]+) '
    r'options=(?P<options>\[.*\])$'
))
def _when_create_happy(ctx, operator, name, team, options):
    _run_create(ctx, operator, name, team, options, expect_error=False)


@when(parsers.re(
    r'管理员 "(?P<operator>[^"]+)" 尝试创建选项库 name="(?P<name>[^"]*)" team=(?P<team>[^ ]+) '
    r'options=(?P<options>\[.*\])$'
))
def _when_create_corner(ctx, operator, name, team, options):
    _run_create(ctx, operator, name, team, options, expect_error=True)


def _run_update(ctx, operator, library_id, payload_str, *, expect_error: bool):
    payload = {}
    # 支持两类字段：name="x" 或 options=[...]
    if payload_str.startswith("name="):
        payload["name"] = payload_str[len("name="):].strip().strip('"')
    elif payload_str.startswith("options="):
        payload["options"] = _parse_options(payload_str[len("options="):])
    else:
        raise AssertionError(f"unsupported payload: {payload_str!r}")

    if expect_error:
        try:
            ctx["result"] = svc.update_library(library_id, payload, operator)
        except BaseAppException as exc:
            ctx["error"] = exc
    else:
        ctx["result"] = svc.update_library(library_id, payload, operator)


@when(parsers.re(
    r'管理员 "(?P<operator>[^"]+)" 更新选项库 "(?P<library_id>[^"]+)" 字段 (?P<payload>.+)$'
))
def _when_update_happy(ctx, operator, library_id, payload):
    _run_update(ctx, operator, library_id, payload, expect_error=False)


@when(parsers.re(
    r'管理员 "(?P<operator>[^"]+)" 尝试更新选项库 "(?P<library_id>[^"]+)" 字段 (?P<payload>.+)$'
))
def _when_update_corner(ctx, operator, library_id, payload):
    _run_update(ctx, operator, library_id, payload, expect_error=True)


def _run_delete(ctx, operator, library_id, *, expect_error: bool):
    if expect_error:
        try:
            svc.delete_library(library_id, operator)
        except BaseAppException as exc:
            ctx["error"] = exc
    else:
        svc.delete_library(library_id, operator)


@when(parsers.parse('管理员 "{operator}" 删除选项库 "{library_id}"'))
def _when_delete_happy(ctx, operator, library_id):
    _run_delete(ctx, operator, library_id, expect_error=False)


@when(parsers.parse('管理员 "{operator}" 尝试删除选项库 "{library_id}"'))
def _when_delete_corner(ctx, operator, library_id):
    _run_delete(ctx, operator, library_id, expect_error=True)


@when(parsers.re(r'当前用户以团队 \[(?P<team>[^\]]*)\] 调用 list_libraries'))
def _when_list(ctx, team):
    ids = [int(t.strip()) for t in team.split(",") if t.strip()]
    ctx["list_result"] = svc.list_libraries(team=ids)


# ---------------------------------------------------------------------------
# 那么 (Then): 断言
# ---------------------------------------------------------------------------

@then("创建应当成功")
@then("更新应当成功")
@then("删除应当成功")
def _no_error(ctx):
    assert ctx["error"] is None, f"unexpected error: {ctx['error']}"


@then(parsers.parse('返回结果的 name 应当为 "{name}"'))
def _result_name(ctx, name):
    assert ctx["result"]["name"] == name


@then(parsers.parse("返回结果的 options 数量应当为 {count:d}"))
def _result_options_count(ctx, count):
    assert len(ctx["result"]["options"]) == count


@then("数据库中应当存在 library_id 对应的记录")
def _db_has_library(ctx):
    assert PublicEnumLibrary.objects.filter(library_id=ctx["library_id"]).exists()


@then(parsers.parse("快照同步任务应当被触发 {count:d} 次"))
def _snapshot_count(ctx, count):
    assert len(ctx["snapshot_calls"]) == count, ctx["snapshot_calls"]


@then(parsers.parse('数据库中 "{library_id}" 的名称应当为 "{name}"'))
def _db_name(library_id, name):
    assert PublicEnumLibrary.objects.get(library_id=library_id).name == name


@then(parsers.parse('数据库中不应再存在 "{library_id}"'))
def _db_absent(library_id):
    assert not PublicEnumLibrary.objects.filter(library_id=library_id).exists()


@then(parsers.parse("返回的选项库数量应当为 {count:d}"))
def _list_count(ctx, count):
    assert len(ctx["list_result"]) == count


@then(parsers.parse('选项库 "{library_id}" 的 editable 应当为 {flag}'))
def _list_editable(ctx, library_id, flag):
    expected = flag.lower() == "true"
    record = next(r for r in ctx["list_result"] if r["library_id"] == library_id)
    assert record["editable"] is expected, record


@then(parsers.parse('应当抛出业务异常，消息包含 "{snippet}"'))
def _expect_error(ctx, snippet):
    assert ctx["error"] is not None, "expected BaseAppException, got none"
    assert snippet in str(ctx["error"]), ctx["error"]


@then(parsers.parse("异常数据中的 references 长度应当为 {count:d}"))
def _error_refs_len(ctx, count):
    data = getattr(ctx["error"], "data", None) or {}
    assert len(data.get("references", [])) == count, data


@then(parsers.parse('数据库中仍然存在 "{library_id}"'))
def _db_still_exists(library_id):
    assert PublicEnumLibrary.objects.filter(library_id=library_id).exists()
