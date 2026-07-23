"""CMDB 公共枚举库服务覆盖测试（DB + fake_graph 桩 query_entity/set_entity_properties）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：公共选项库 CRUD、选项校验、引用扫描、快照同步。
"""

import json

import pytest

from apps.cmdb.models.public_enum_library import PublicEnumLibrary
from apps.cmdb.services import public_enum_library as svc
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.public_enum_library"


@pytest.fixture
def patch_parse(monkeypatch):
    # parse_attrs 默认走真实 JSON 解析即可；此处仅确保 search 不触图库
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.parse_attrs",
        lambda raw: json.loads(raw) if isinstance(raw, str) else (raw or []),
    )


def _make(library_id="lib_1", team=None, options=None):
    return PublicEnumLibrary.objects.create(
        library_id=library_id, name="状态库", team=team or [1],
        options=options or [{"id": "1", "name": "运行"}], created_by="admin", updated_by="admin",
    )


# --------------------------------------------------------------------------
# _validate_options
# --------------------------------------------------------------------------


def test_validate_options_not_list():
    with pytest.raises(BaseAppException):
        svc._validate_options("x")


def test_validate_options_bad_item():
    with pytest.raises(BaseAppException):
        svc._validate_options(["x"])


def test_validate_options_missing_id():
    with pytest.raises(BaseAppException):
        svc._validate_options([{"name": "n"}])


def test_validate_options_dup_id():
    with pytest.raises(BaseAppException):
        svc._validate_options([{"id": "1", "name": "a"}, {"id": "1", "name": "b"}])


def test_validate_options_ok():
    svc._validate_options([{"id": "1", "name": "a"}])


def test_generate_library_id():
    assert svc._generate_library_id().startswith("lib_")


# --------------------------------------------------------------------------
# create_library
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_library_ok():
    result = svc.create_library({"name": "状态", "team": [1], "options": [{"id": "1", "name": "运行"}]}, "admin")
    assert result["name"] == "状态"
    assert result["library_id"].startswith("lib_")


@pytest.mark.django_db
def test_create_library_empty_name():
    with pytest.raises(BaseAppException):
        svc.create_library({"name": "  "}, "admin")


@pytest.mark.django_db
def test_create_library_bad_team():
    with pytest.raises(BaseAppException):
        svc.create_library({"name": "x", "team": "notlist"}, "admin")


# --------------------------------------------------------------------------
# update_library
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_library_not_found():
    with pytest.raises(BaseAppException):
        svc.update_library("absent", {"name": "x"}, "admin")


@pytest.mark.django_db
def test_update_library_name_team(monkeypatch):
    _make()
    result = svc.update_library("lib_1", {"name": "新名", "team": [2]}, "bob")
    assert result["name"] == "新名"
    assert result["team"] == [2]
    assert result["updated_by"] == "bob"


@pytest.mark.django_db
def test_update_library_empty_name():
    _make()
    with pytest.raises(BaseAppException):
        svc.update_library("lib_1", {"name": ""}, "admin")


@pytest.mark.django_db
def test_update_library_options_enqueues(monkeypatch):
    _make()
    called = {}
    monkeypatch.setattr(
        f"{MODULE}.enqueue_library_snapshot_refresh",
        lambda library_id, trigger, operator: called.setdefault("hit", True),
    )
    result = svc.update_library("lib_1", {"options": [{"id": "2", "name": "停止"}]}, "admin")
    assert result["options"][0]["id"] == "2"
    assert called.get("hit") is True


# --------------------------------------------------------------------------
# list_libraries
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_libraries_editable():
    _make(team=[1])
    libs = svc.list_libraries(team=[1])
    assert libs[0]["editable"] is True


@pytest.mark.django_db
def test_list_libraries_not_editable():
    _make(team=[9])
    libs = svc.list_libraries(team=[1])
    assert libs[0]["editable"] is False


@pytest.mark.django_db
def test_get_library_or_raise():
    _make()
    assert svc.get_library_or_raise("lib_1").library_id == "lib_1"
    with pytest.raises(BaseAppException):
        svc.get_library_or_raise("absent")


# --------------------------------------------------------------------------
# find_library_references（fake_graph）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_find_library_references(patch_parse, fake_graph):
    models = [
        {
            "model_id": "host", "model_name": "主机",
            "attrs": json.dumps([
                {"attr_id": "status", "attr_name": "状态", "attr_type": "enum",
                 "enum_rule_type": "public_library", "public_library_id": "lib_1"},
                {"attr_id": "name", "attr_type": "str"},
            ]),
        }
    ]
    fake_graph(MODULE, query_entity=(models, 1))
    refs = svc.find_library_references("lib_1")
    assert len(refs) == 1
    assert refs[0]["attr_id"] == "status"


@pytest.mark.django_db
def test_find_library_references_none(patch_parse, fake_graph):
    fake_graph(MODULE, query_entity=([], 0))
    assert svc.find_library_references("lib_1") == []


# --------------------------------------------------------------------------
# delete_library
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_library_blocked_by_reference(monkeypatch):
    _make()
    monkeypatch.setattr(
        f"{MODULE}.find_library_references",
        lambda lib: [{"model_id": "host", "model_name": "主机", "attr_id": "s", "attr_name": "状态"}],
    )
    with pytest.raises(BaseAppException) as exc:
        svc.delete_library("lib_1", "admin")
    assert exc.value.data and "references" in exc.value.data


@pytest.mark.django_db
def test_delete_library_ok(monkeypatch):
    _make()
    monkeypatch.setattr(f"{MODULE}.find_library_references", lambda lib: [])
    svc.delete_library("lib_1", "admin")
    assert not PublicEnumLibrary.objects.filter(library_id="lib_1").exists()


@pytest.mark.django_db
def test_delete_library_not_found():
    with pytest.raises(BaseAppException):
        svc.delete_library("absent", "admin")


# --------------------------------------------------------------------------
# sync_library_snapshots（fake_graph）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_sync_library_snapshots_not_found(fake_graph):
    fake_graph(MODULE)
    result = svc.sync_library_snapshots("absent", "update")
    assert result["result"] is False


@pytest.mark.django_db
def test_sync_library_snapshots_ok(patch_parse, fake_graph):
    _make(options=[{"id": "2", "name": "停止"}])
    models = [
        {
            "model_id": "host", "_id": 1, "model_name": "主机",
            "attrs": json.dumps([
                {"attr_id": "status", "attr_type": "enum",
                 "enum_rule_type": "public_library", "public_library_id": "lib_1", "option": []},
            ]),
        }
    ]
    fg = fake_graph(MODULE, query_entity=(models, 1))
    result = svc.sync_library_snapshots("lib_1", "update", "admin")
    assert result["result"] is True
    assert result["affected_attrs"] == 1
    assert any(c[0] == "set_entity_properties" for c in fg.calls)


@pytest.mark.django_db
def test_sync_library_snapshots_reports_partial_graph_failure(patch_parse, fake_graph):
    _make(options=[{"id": "2", "name": "停止"}])
    models = [
        {
            "model_id": model_id,
            "_id": model_db_id,
            "attrs": json.dumps(
                [
                    {
                        "attr_id": "status",
                        "attr_type": "enum",
                        "enum_rule_type": "public_library",
                        "public_library_id": "lib_1",
                        "option": [],
                    }
                ]
            ),
        }
        for model_id, model_db_id in (("host", 1), ("service", 2))
    ]

    def _set_entity_properties(_label, ids, *_args):
        if ids == [2]:
            raise RuntimeError("graph unavailable")
        return {}

    fake_graph(
        MODULE,
        query_entity=(models, 2),
        set_entity_properties=_set_entity_properties,
    )

    result = svc.sync_library_snapshots("lib_1", "update", "admin")

    assert result["result"] is False
    assert result["affected_models"] == 1
    assert result["failed_count"] == 1
    assert result["failed_items"] == [
        {"model_id": "service", "error": "graph unavailable"}
    ]


def test_snapshot_task_retries_partial_graph_failure(mocker):
    from celery.canvas import Signature
    from celery.exceptions import Retry

    from apps.cmdb.tasks import celery_tasks

    mocker.patch(
        f"{MODULE}.sync_library_snapshots",
        return_value={
            "result": False,
            "library_id": "lib_1",
            "failed_count": 1,
            "failed_items": [{"model_id": "service", "error": "graph unavailable"}],
        },
    )
    apply_async = mocker.patch.object(Signature, "apply_async", autospec=True)
    task = celery_tasks.sync_public_enum_library_snapshots_task
    task.push_request(
        args=("lib_1", "update", "admin"),
        kwargs={},
        id="public-enum-snapshot-retry-1",
        retries=0,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(Retry) as retry_error:
            task.run("lib_1", "update", "admin")
    finally:
        task.pop_request()

    scheduled_signature = apply_async.call_args.args[0]
    expected_countdown = celery_tasks.PUBLIC_ENUM_SNAPSHOT_RETRY_BASE_SECONDS
    assert retry_error.value.when == expected_countdown
    assert scheduled_signature.options["countdown"] == expected_countdown
    assert scheduled_signature.options["retries"] == 1
    assert task.max_retries == celery_tasks.PUBLIC_ENUM_SNAPSHOT_MAX_RETRIES


def test_snapshot_task_raises_after_partial_failure_retries_exhausted(mocker):
    from apps.cmdb.tasks import celery_tasks

    mocker.patch(
        f"{MODULE}.sync_library_snapshots",
        return_value={
            "result": False,
            "library_id": "lib_1",
            "failed_count": 1,
            "failed_items": [{"model_id": "service", "error": "graph unavailable"}],
        },
    )
    task = celery_tasks.sync_public_enum_library_snapshots_task
    task.push_request(
        args=("lib_1", "update", "admin"),
        kwargs={},
        id="public-enum-snapshot-retry-exhausted",
        retries=task.max_retries,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(RuntimeError, match=r"failed_count=1"):
            task.run("lib_1", "update", "admin")
    finally:
        task.pop_request()


def test_snapshot_task_preserves_success_result(mocker):
    from apps.cmdb.tasks import celery_tasks

    expected = {
        "result": True,
        "library_id": "lib_1",
        "affected_models": 2,
        "affected_attrs": 2,
        "failed_count": 0,
        "failed_items": [],
    }
    mocker.patch(f"{MODULE}.sync_library_snapshots", return_value=expected)
    retry = mocker.patch.object(
        celery_tasks.sync_public_enum_library_snapshots_task, "retry"
    )

    result = celery_tasks.sync_public_enum_library_snapshots_task.run(
        "lib_1", "update", "admin"
    )

    assert result == expected
    retry.assert_not_called()
