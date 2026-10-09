import io

import openpyxl

from apps.cmdb.utils.Import import Import


def test_transfer_rows_preserve_zero_and_name_the_failing_column(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_search", lambda *a, **k: [])
    importer = Import(
        "host",
        [{"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"}, {"attr_id": "count", "attr_name": "数量", "attr_type": "int"}],
        [],
        "admin",
    )
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "host"
    for row in (
        ["提示", "实例名", "数量"],
        ["类型", "str", "int"],
        ["字段标识(请勿编辑)", "inst_name", "count"],
        [None, "one", 0],
        [None, "two", "PRIVATE-CELL-SENTINEL"],
    ):
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    rows = list(importer.iter_transfer_rows(stream, [1]))
    assert rows[0] == (4, {"model_id": "host", "inst_name": "one", "count": 0}, {}, [])
    assert rows[1][0] == 5
    column, field_id, reason = rows[1][3][0]
    assert column == "C 数量"
    assert field_id == "count"
    assert reason == "第5行，字段'数量'的值'PRIVATE-CELL-SENTINEL'格式错误"


def test_user_and_organization_none_is_skipped_and_user_matches_username(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_search", lambda *a, **k: [])
    importer = Import(
        "system",
        [
            {"attr_id": "inst_name", "attr_name": "系统名称", "attr_type": "str"},
            {
                "attr_id": "operator",
                "attr_name": "运维人员",
                "attr_type": "user",
                "option": [{"id": 7, "name": "alice", "username": "alice", "display_name": "张三"}],
            },
            {
                "attr_id": "developer",
                "attr_name": "开发人员",
                "attr_type": "user",
                "option": [{"id": 7, "name": "alice", "username": "alice", "display_name": "张三"}],
            },
            {
                "attr_id": "organization",
                "attr_name": "组织",
                "attr_type": "organization",
                "option": [{"id": 1, "name": "Default"}],
            },
        ],
        [],
        "admin",
    )
    book = openpyxl.Workbook()
    sheet = book.active
    for row in (
        ["提示", "系统名称", "运维人员", "开发人员", "组织"],
        ["类型", "字符串", "用户", "用户", "组织"],
        ["字段标识(请勿编辑)", "inst_name", "operator", "developer", "organization"],
        [None, "sys-empty", "None", "None", "None"],
        [None, "sys-user", "张三(alice)", None, None],
        [None, "sys-id", "7", None, None],
    ):
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    rows = list(importer.iter_transfer_rows(stream, [1]))
    assert rows[0][1] == {"model_id": "system", "inst_name": "sys-empty"}
    assert rows[0][3] == []
    assert rows[1][1]["operator"] == [7]
    assert rows[1][3] == []
    column, field_id, reason = rows[2][3][0]
    assert field_id == "operator"
    assert column.endswith("运维人员")
    assert "7" in reason


def test_run_keeps_other_rows_when_one_unique_field_conflicts(monkeypatch):
    from types import SimpleNamespace

    from apps.cmdb.services.instance import InstanceManage
    from apps.cmdb.services.operation_service import OperationService
    from apps.cmdb.services.transfer_authorization import TransferAuthorization
    from apps.cmdb.services.transfer_import import TransferImport
    from apps.cmdb.utils.Import import Import

    attrs = [
        {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str", "is_only": True, "is_required": True, "editable": True},
        {"attr_id": "serial", "attr_name": "编号", "attr_type": "str", "is_only": True, "is_required": True, "editable": True},
    ]
    existing = {"_id": 1, "inst_uuid": "11111111-1111-4111-8111-111111111111", "inst_name": "one", "serial": "IT-225"}
    created = []
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr_v2", lambda *a, **k: attrs)
    monkeypatch.setattr(Import, "get_model_asso_map", lambda self: {})
    monkeypatch.setattr(
        Import,
        "iter_transfer_rows",
        lambda self, stream, teams: [
            (4, {"model_id": "host", "inst_name": "one", "serial": "-225"}, {}, []),
            (5, {"model_id": "host", "inst_name": "two", "serial": "NEW-1"}, {}, []),
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.build_unique_rule_context",
        lambda _: SimpleNamespace(unique_rules=[], attrs_by_id={item["attr_id"]: item for item in attrs}),
    )

    class DummyGraph:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query_entity(self, label, params, **kwargs):
            fields = {item["field"] for item in params}
            if "inst_name" in fields and "serial" in fields:
                return [], 0
            if "inst_name" in fields:
                return [existing], 0
            return [], 0

    monkeypatch.setattr("apps.cmdb.services.transfer_import.GraphClient", lambda *a, **k: DummyGraph())
    monkeypatch.setattr(TransferAuthorization, "revalidate", lambda task: context)
    monkeypatch.setattr(TransferAuthorization, "check_instance", lambda *a, **k: None)
    monkeypatch.setattr("apps.cmdb.services.transfer_import.load_attribute_snapshot", lambda *a, **k: {})
    monkeypatch.setattr(OperationService, "start", lambda **kw: SimpleNamespace(operation=SimpleNamespace()))
    monkeypatch.setattr(OperationService, "events_for_operation", lambda operation: [])

    def execute_graph(operation, graph_write, events):
        result = graph_write("op-1")
        created.append(result)
        return result

    monkeypatch.setattr(OperationService, "execute_graph", execute_graph)
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda model, data, operator, **kw: {**data, "inst_uuid": "22222222-2222-4222-8222-222222222222"},
    )
    task = SimpleNamespace(pk="task-1", model_id="host", team_id=1)
    context = SimpleNamespace(actor=SimpleNamespace(username="admin", roles=["admin"]), teams=[1], associations=[])
    summary, errors = TransferImport.run(task, stream=None, context=context, progress=lambda *a: None)
    assert summary["created"] == 1
    assert summary["failed_rows"] == 1
    assert summary["updated"] == 0
    assert created[0]["inst_name"] == "two"
    assert errors[0][0] == 4
    assert errors[0][2] == "inst_name"
    assert "实例名" in errors[0][3]


def test_run_updates_when_all_unique_fields_match(monkeypatch):
    from types import SimpleNamespace

    from apps.cmdb.services.instance import InstanceManage
    from apps.cmdb.services.operation_service import OperationService
    from apps.cmdb.services.transfer_authorization import TransferAuthorization
    from apps.cmdb.services.transfer_import import TransferImport
    from apps.cmdb.utils.Import import Import

    attrs = [
        {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str", "is_only": True, "is_required": True, "editable": True},
        {"attr_id": "serial", "attr_name": "编号", "attr_type": "str", "is_only": True, "is_required": True, "editable": True},
    ]
    existing = {
        "_id": 1,
        "inst_uuid": "11111111-1111-4111-8111-111111111111",
        "inst_name": "one",
        "serial": "IT-225",
        "organization": [1],
    }
    updated = []
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr_v2", lambda *a, **k: attrs)
    monkeypatch.setattr(Import, "get_model_asso_map", lambda self: {})
    monkeypatch.setattr(
        Import,
        "iter_transfer_rows",
        lambda self, stream, teams: [(4, {"model_id": "host", "inst_name": "one", "serial": "IT-225", "comment": "changed"}, {}, [])],
    )
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.build_unique_rule_context",
        lambda _: SimpleNamespace(unique_rules=[], attrs_by_id={item["attr_id"]: item for item in attrs}),
    )

    class DummyGraph:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query_entity(self, label, params, **kwargs):
            return [existing], 0

    monkeypatch.setattr("apps.cmdb.services.transfer_import.GraphClient", lambda *a, **k: DummyGraph())
    monkeypatch.setattr(TransferAuthorization, "revalidate", lambda task: context)
    monkeypatch.setattr(TransferAuthorization, "check_instance", lambda *a, **k: None)
    monkeypatch.setattr("apps.cmdb.services.transfer_import.load_attribute_snapshot", lambda *a, **k: {})
    monkeypatch.setattr(OperationService, "start", lambda **kw: SimpleNamespace(operation=SimpleNamespace()))
    monkeypatch.setattr(OperationService, "events_for_operation", lambda operation: [])
    monkeypatch.setattr(OperationService, "execute_graph", lambda operation, graph_write, events: graph_write("op-1"))
    monkeypatch.setattr(
        InstanceManage,
        "instance_update_by_uuid",
        lambda teams, roles, uuid, data, operator, **kw: updated.append(data) or {**existing, **data},
    )
    monkeypatch.setattr(InstanceManage, "instance_create", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should update")))
    task = SimpleNamespace(pk="task-1", model_id="host", team_id=1)
    context = SimpleNamespace(actor=SimpleNamespace(username="admin", roles=["admin"]), teams=[1], associations=[])
    summary, errors = TransferImport.run(task, stream=None, context=context, progress=lambda *a: None)
    assert summary == {"created": 0, "updated": 1, "failed_rows": 0, "created_relations": 0, "failed_relations": 0}
    assert errors == []
    assert updated[0]["inst_name"] == "one"
    assert updated[0]["serial"] == "IT-225"


def test_unique_write_failure_only_matches_pre_write_unique_errors():
    from apps.cmdb.services.transfer_import import TransferImport
    from apps.core.exceptions.base_app_exception import BaseAppException

    check = {"is_only": {"inst_name": "实例名", "serial": "编号"}}
    assert TransferImport._unique_write_failure(BaseAppException("实例名 exist；"), check) == ("inst_name", "实例名已存在")
    assert TransferImport._unique_write_failure(BaseAppException("规则 1【编号】与现有实例冲突：编号=-225"), check) == (
        "serial",
        "规则 1【编号】与现有实例冲突：编号=-225",
    )
    assert TransferImport._unique_write_failure(BaseAppException("图写入超时"), check) is None


def test_credential_reason_omits_submitted_value():
    from apps.cmdb.services.transfer_execution import TransferExecution
    from apps.cmdb.services.transfer_import import TransferImport

    reason = TransferImport._public_reason("password", "第4行，字段'密码'的值'SECRET-CELL'格式错误")
    assert reason == "凭据字段格式不正确"
    assert "SECRET-CELL" not in reason
    assert TransferExecution._excel_text("=1+1") == "'=1+1"
    assert TransferExecution._excel_text("数量") == "数量"
