import logging

from apps.module_link.services.backfill import backfill_monitor_ids

QUERY = "apps.module_link.services.backfill.InstanceManage.query_entity_by_uuid"
BACKFILL = "apps.module_link.services.backfill.CmdbToMonitorPushService._backfill_monitor_id"
DONE = "event=module_link_cmdb_id_backfill_completed count=%s"
FAILED = "event=module_link_cmdb_id_backfill_failed inst_uuid=%s failed_stage=%s error_type=%s"


def test_backfill_writes_monitor_id(mocker, caplog):
    entity = {"inst_uuid": "ci-1", "_id": 9, "model_id": "host"}
    mocker.patch(QUERY, return_value=entity)
    backfill = mocker.patch(BACKFILL, return_value={**entity, "monitor_id": "m-1"})
    with caplog.at_level(logging.INFO, logger="module-link"):
        assert (
            backfill_monitor_ids(
                [("ci-1", "m-1")],
                {"username": "alice", "current_team": 1},
            )
            == 1
        )
    backfill.assert_called_once()
    assert backfill.call_args.kwargs["operator"] == "alice"
    records = [row for row in caplog.records if row.msg == DONE]
    assert records[0].args == (1,)


def test_backfill_skips_empty_and_logs_query_failure(mocker, caplog):
    secret = "SECRET-PAYLOAD-DO-NOT-LOG"
    mocker.patch(QUERY, side_effect=RuntimeError(secret))
    backfill = mocker.patch(BACKFILL)
    with caplog.at_level(logging.ERROR, logger="module-link"):
        assert backfill_monitor_ids([("", "m-1"), ("ci-1", "m-1")]) == 0
    backfill.assert_not_called()
    records = [row for row in caplog.records if row.msg == FAILED]
    assert len(records) == 1
    assert records[0].args == ("ci-1", "query_entity", "RuntimeError")
    formatted = logging.Formatter().format(records[0])
    assert secret not in formatted
    assert secret not in records[0].getMessage()
