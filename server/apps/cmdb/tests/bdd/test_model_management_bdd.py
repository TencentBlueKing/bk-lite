"""CMDB 模型管理 BDD（中文 Gherkin）。

对照 spec/prd/CMDB·模型管理：
- 模型分类（ClassificationManage）CRUD：创建/更新/查询时图库交互行为；
- 模型（ModelManage）删除前的引用校验：实例存在 / 关联存在；
- 更新模型时 model_id 是不可变字段；
- 分类列表 exist_model 标记。

3 happy + 5 corner。复用 apps/cmdb/tests/conftest.py 中的 FakeGraphClient 模式。
"""

from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException

FEATURE = str(Path(__file__).parent / "model_management.feature")
scenarios(FEATURE)


# ---------------------------------------------------------------------------
# FakeGraphClient — 共用配方
# ---------------------------------------------------------------------------

class _FakeGraph:
    """记录调用并按 entity_type/method 调度返回值。"""

    def __init__(self):
        self.classifications: list[dict] = []
        self.models: list[dict] = []
        self.instances_count_by_model: dict[str, int] = {}
        self.associations_by_model: dict[str, list] = {}
        self.calls: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    # ----- 查询 -----
    def query_entity(self, entity_type, params, page=None):
        self.calls.append(("query_entity", entity_type, params, page))
        if entity_type == "classification":
            return list(self.classifications), len(self.classifications)
        if entity_type == "model":
            # 按 classification_id 过滤（用于 check_classification_is_used）
            for p in params or []:
                if p.get("field") == "classification_id":
                    matched = [m for m in self.models if m.get("classification_id") == p["value"]]
                    return matched, len(matched)
                if p.get("field") == "model_id" and p.get("type") == "str=":
                    matched = [m for m in self.models if m.get("model_id") == p["value"]]
                    return matched, len(matched)
                if p.get("field") == "model_id" and p.get("type") == "str<>":
                    matched = [m for m in self.models if m.get("model_id") != p["value"]]
                    return matched, len(matched)
            return list(self.models), len(self.models)
        if entity_type == "instance":
            for p in params or []:
                if p.get("field") == "model_id":
                    cnt = self.instances_count_by_model.get(p["value"], 0)
                    return [{"_id": 1, "model_id": p["value"]}] * (1 if cnt else 0), cnt
            return [], 0
        return [], 0

    # ----- 写入 -----
    def create_entity(self, entity_type, data, check_attr_map, exist_items, *args, **kwargs):
        self.calls.append(("create_entity", entity_type, data, exist_items))
        record = dict(data)
        record["_id"] = len(self.classifications) + 100 if entity_type == "classification" else len(self.models) + 200
        if entity_type == "classification":
            self.classifications.append(record)
        elif entity_type == "model":
            self.models.append(record)
        return record

    def set_entity_properties(self, entity_type, ids, data, check_attr_map, exist_items):
        self.calls.append(("set_entity_properties", entity_type, ids, data, exist_items))
        return [dict(_id=ids[0], **data)]

    def create_edge(self, *args, **kwargs):
        self.calls.append(("create_edge",) + args)
        return {}

    def batch_delete_entity(self, *args, **kwargs):
        self.calls.append(("batch_delete_entity",) + args)
        return None

    # 工具：取最后一次某方法的调用
    def last(self, method):
        for call in reversed(self.calls):
            if call[0] == method:
                return call
        raise AssertionError(f"no call to {method}: {self.calls}")


@pytest.fixture
def fake():
    return _FakeGraph()


@pytest.fixture(autouse=True)
def _patch_graphclient(monkeypatch, fake):
    """所有目标服务模块的 GraphClient 都替换为同一份 fake，保证调用记录可观测。"""
    for module in (
        "apps.cmdb.services.classification",
        "apps.cmdb.services.model",
    ):
        monkeypatch.setattr(f"{module}.GraphClient", lambda *a, **k: fake)


@pytest.fixture
def ctx():
    return {"result": None, "error": None}


# ---------------------------------------------------------------------------
# 背景
# ---------------------------------------------------------------------------

@given("图库可以被 FakeGraphClient 替换")
def _bg_ok(fake):
    assert fake is not None


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse('图库中已存在分类记录 _id={cid:d} classification_id="{classification_id}" classification_name="{name}"'))
def _seed_classification(fake, cid, classification_id, name):
    fake.classifications.append({"_id": cid, "classification_id": classification_id, "classification_name": name})


@given(parsers.parse('图库中已存在模型记录 model_id="{model_id}" classification_id="{classification_id}"'))
def _seed_model(fake, model_id, classification_id):
    fake.models.append({"_id": 200 + len(fake.models), "model_id": model_id, "classification_id": classification_id})


@given(parsers.parse('图库中存在 model_id="{model_id}" 的实例 {count:d} 条'))
def _seed_instances(fake, model_id, count):
    fake.instances_count_by_model[model_id] = count


@given(parsers.parse('模型 "{model_id}" 存在关联边 {count:d} 条'))
def _seed_assoc(monkeypatch, model_id, count):
    monkeypatch.setattr(
        ModelManage,
        "model_association_search",
        staticmethod(lambda mid: [{"_id": 1}] * count if mid == model_id else []),
    )


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.parse('管理员创建模型分类 classification_id="{cid}" classification_name="{name}"'))
def _create_classification(ctx, cid, name):
    ctx["result"] = ClassificationManage.create_model_classification(
        {"classification_id": cid, "classification_name": name}
    )


@when(parsers.parse('管理员更新分类 _id={cid:d} 字段 classification_name="{name}"'))
def _update_classification(ctx, cid, name):
    ctx["result"] = ClassificationManage.update_model_classification(cid, {"classification_name": name})


@when("用户查询模型分类列表")
def _search_classifications(ctx):
    ctx["result"] = ClassificationManage.search_model_classification()


@when(parsers.parse('管理员尝试校验分类 "{cid}" 是否被使用'))
def _check_classification(ctx, cid):
    try:
        ClassificationManage.check_classification_is_used(cid)
        ctx["result"] = "ok"
    except BaseAppException as exc:
        ctx["error"] = exc


@when(parsers.parse('管理员尝试校验模型 "{mid}" 是否存在实例'))
def _check_model_inst(ctx, mid):
    try:
        ModelManage.check_model_exist_inst(mid)
        ctx["result"] = "ok"
    except BaseAppException as exc:
        ctx["error"] = exc


@when(parsers.parse('管理员尝试校验模型 "{mid}" 是否存在关联'))
def _check_model_assoc(ctx, mid):
    try:
        ModelManage.check_model_exist_association(mid)
        ctx["result"] = "ok"
    except BaseAppException as exc:
        ctx["error"] = exc


@when(parsers.parse('管理员更新模型 _id={mid:d} 字段 model_id="{model_id}" model_name="{name}"'))
def _update_model(ctx, mid, model_id, name):
    ctx["result"] = ModelManage.update_model(mid, {"model_id": model_id, "model_name": name})


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then(parsers.parse('应当对图库 "{entity_type}" 执行 {count:d} 次 create_entity'))
def _assert_create_count(fake, entity_type, count):
    actual = sum(1 for c in fake.calls if c[0] == "create_entity" and c[1] == entity_type)
    assert actual == count, f"create_entity({entity_type}) expected {count} actual {actual} calls={fake.calls}"


@then(parsers.parse('返回的分类应包含 classification_id="{cid}"'))
def _result_has_cid(ctx, cid):
    assert ctx["result"]["classification_id"] == cid


@then(parsers.parse("set_entity_properties 调用时 exist_items 不应包含 _id={cid:d}"))
def _set_properties_excludes_self(fake, cid):
    call = fake.last("set_entity_properties")
    exist_items = call[4]
    assert all(item["_id"] != cid for item in exist_items), exist_items


@then(parsers.parse('分类 "{cid}" 的 exist_model 应当为 {flag}'))
def _classification_exist_model(ctx, cid, flag):
    expected = flag.lower() == "true"
    record = next(c for c in ctx["result"] if c["classification_id"] == cid)
    assert record["exist_model"] is expected, record


@then(parsers.parse('应当抛出业务异常，消息包含 "{snippet}"'))
def _expect_error(ctx, snippet):
    assert ctx["error"] is not None, "expected BaseAppException, got none"
    assert snippet in str(ctx["error"]), ctx["error"]


@then("校验应当通过")
def _check_ok(ctx):
    assert ctx["error"] is None
    assert ctx["result"] == "ok"


@then(parsers.parse('set_entity_properties 调用时 payload 中不应包含 "{key}"'))
def _payload_missing(fake, key):
    call = fake.last("set_entity_properties")
    payload = call[3]
    assert key not in payload, payload


@then(parsers.parse('set_entity_properties 调用时 payload 中应包含 "{key}"'))
def _payload_has(fake, key):
    call = fake.last("set_entity_properties")
    payload = call[3]
    assert key in payload, payload
