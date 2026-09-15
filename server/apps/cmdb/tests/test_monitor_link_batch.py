"""CMDB 批量同步监控：走现有无凭据推送并汇总结果。"""

import logging

import pytest

from apps.cmdb.services.monitor_link import BATCH_PUSH_LIMIT, MonitorLinkService

QUERY_PATH = "apps.cmdb.services.monitor_link.InstanceManage.query_entity_by_uuid"
PUSH_PATH = "apps.cmdb.services.monitor_link.CmdbToMonitorPushService.push_instance"

ACTOR_SCOPE = {"allowed_org_ids": [1], "operator": "alice"}
ROW_FAILED_TEMPLATE = "event=cmdb_monitor_link_row_failed inst_uuid=%s failed_stage=%s error_type=%s"
BATCH_DONE_TEMPLATE = "event=cmdb_monitor_link_batch_completed total=%s ok=%s already_linked=%s " "not_found=%s conflict=%s failed=%s"


def _entity(inst_uuid, *, model_id="host", monitor_id=None, **extra):
    row = {"inst_uuid": inst_uuid, "model_id": model_id}
    if monitor_id is not None:
        row["monitor_id"] = monitor_id
    row.update(extra)
    return row


def _empty_summary(**overrides):
    payload = {
        "total": 0,
        "ok": 0,
        "already_linked": 0,
        "not_found": 0,
        "conflict": 0,
        "failed": 0,
        "results": [],
    }
    payload.update(overrides)
    return payload


def test_already_linked_skips_push(mocker):
    query = mocker.patch(QUERY_PATH, return_value=_entity("u-linked", monitor_id="m-keep"))
    push = mocker.patch(PUSH_PATH)

    result = MonitorLinkService.batch_push(["u-linked"], actor_scope=ACTOR_SCOPE)

    assert result == _empty_summary(
        total=1,
        already_linked=1,
        results=[{"inst_uuid": "u-linked", "status": "already_linked", "monitor_id": "m-keep"}],
    )
    query.assert_called_once_with("u-linked")
    push.assert_not_called()


def test_unlinked_push_ok(mocker):
    mocker.patch(QUERY_PATH, return_value=_entity("u-ok"))
    push = mocker.patch(
        PUSH_PATH,
        return_value={"link_status": "ok", "monitor_id": "m-new", "cmdb_id": "u-ok"},
    )

    result = MonitorLinkService.batch_push(["u-ok"], actor_scope=ACTOR_SCOPE)

    assert result == _empty_summary(
        total=1,
        ok=1,
        results=[{"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-new"}],
    )
    push.assert_called_once_with("u-ok", actor_scope=ACTOR_SCOPE)


def test_not_found_and_conflict_continue(mocker):
    entities = {
        "u-miss": _entity("u-miss"),
        "u-conflict": _entity("u-conflict"),
        "u-ok": _entity("u-ok"),
    }
    mocker.patch(QUERY_PATH, side_effect=lambda inst_uuid: entities[inst_uuid])
    push = mocker.patch(
        PUSH_PATH,
        side_effect=[
            {"link_status": "not_found", "monitor_id": None},
            {"link_status": "conflict", "monitor_id": None},
            {"link_status": "ok", "monitor_id": "m-ok"},
        ],
    )

    result = MonitorLinkService.batch_push(
        ["u-miss", "u-conflict", "u-ok"],
        actor_scope=ACTOR_SCOPE,
    )

    assert result["total"] == 3
    assert result["ok"] == 1
    assert result["not_found"] == 1
    assert result["conflict"] == 1
    assert result["failed"] == 0
    assert result["results"] == [
        {"inst_uuid": "u-miss", "status": "not_found", "monitor_id": None},
        {"inst_uuid": "u-conflict", "status": "conflict", "monitor_id": None},
        {"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-ok"},
    ]
    assert push.call_count == 3


def test_over_limit_raises_value_error(mocker):
    query = mocker.patch(QUERY_PATH)
    push = mocker.patch(PUSH_PATH)
    uuids = [f"u-{i}" for i in range(BATCH_PUSH_LIMIT + 1)]

    with pytest.raises(ValueError):
        MonitorLinkService.batch_push(uuids, actor_scope=ACTOR_SCOPE)

    query.assert_not_called()
    push.assert_not_called()


def test_skipped_model_does_not_push(mocker):
    mocker.patch(QUERY_PATH, return_value=_entity("u-skip", model_id="weblogic"))
    push = mocker.patch(PUSH_PATH)

    result = MonitorLinkService.batch_push(["u-skip"], actor_scope=ACTOR_SCOPE)

    assert result == _empty_summary(
        total=1,
        results=[{"inst_uuid": "u-skip", "status": "skipped_model", "monitor_id": None}],
    )
    assert "skipped_model" not in result
    push.assert_not_called()


def test_missing_entity_is_failed_and_does_not_push(mocker):
    mocker.patch(QUERY_PATH, side_effect=[{}, None])
    push = mocker.patch(PUSH_PATH)

    result = MonitorLinkService.batch_push(["u-empty", "u-none"], actor_scope=ACTOR_SCOPE)

    assert result["total"] == 2
    assert result["failed"] == 2
    assert result["results"] == [
        {"inst_uuid": "u-empty", "status": "failed", "monitor_id": None},
        {"inst_uuid": "u-none", "status": "failed", "monitor_id": None},
    ]
    push.assert_not_called()


def test_push_exception_is_failed_and_continues(mocker, caplog):
    secret = "SECRET-PAYLOAD-DO-NOT-LOG"
    boom = RuntimeError(secret)
    entities = {"u-fail": _entity("u-fail"), "u-ok": _entity("u-ok")}
    mocker.patch(QUERY_PATH, side_effect=lambda inst_uuid: entities[inst_uuid])
    mocker.patch(
        PUSH_PATH,
        side_effect=[boom, {"link_status": "ok", "monitor_id": "m-ok"}],
    )

    with caplog.at_level(logging.DEBUG, logger="cmdb"):
        result = MonitorLinkService.batch_push(["u-fail", "u-ok"], actor_scope=ACTOR_SCOPE)

    assert result == _empty_summary(
        total=2,
        ok=1,
        failed=1,
        results=[
            {"inst_uuid": "u-fail", "status": "failed", "monitor_id": None},
            {"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-ok"},
        ],
    )
    assert boom.args == (secret,)

    error_records = [record for record in caplog.records if record.name == "cmdb" and record.msg == ROW_FAILED_TEMPLATE]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.levelno == logging.ERROR
    assert record.args == ("u-fail", "push_instance", "RuntimeError")
    assert record.getMessage() == ("event=cmdb_monitor_link_row_failed inst_uuid=u-fail failed_stage=push_instance error_type=RuntimeError")
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert record.exc_info[2] is boom.__traceback__
    formatted = logging.Formatter().format(record)
    assert secret not in formatted
    assert secret not in record.getMessage()
    assert secret not in "".join(str(arg) for arg in record.args)

    info_records = [record for record in caplog.records if record.name == "cmdb" and record.msg == BATCH_DONE_TEMPLATE]
    assert len(info_records) == 1
    info = info_records[0]
    assert info.levelno == logging.INFO
    assert info.args == (2, 1, 0, 0, 0, 1)
    assert info.getMessage() == ("event=cmdb_monitor_link_batch_completed total=2 ok=1 already_linked=0 " "not_found=0 conflict=0 failed=1")
    assert secret not in caplog.text
