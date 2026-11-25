import logging

from apps.cmdb.services.collect_snapshot_uuid import normalize_collect_result_payloads


def test_normalize_collect_result_payloads_skips_graph_without_numeric_id(monkeypatch):
    def boom(_ids):
        raise AssertionError("没有数字图 ID 时不应查图")

    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.InstanceManage.query_entity_by_ids",
        staticmethod(boom),
    )

    rewritten = normalize_collect_result_payloads({"add": [{"inst_name": "host-a"}]})

    assert rewritten[0]["add"][0] == {"inst_name": "host-a"}


def test_normalize_collect_result_payloads_adds_inst_uuid(monkeypatch):
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.InstanceManage.query_entity_by_ids",
        staticmethod(lambda ids: [{"_id": 7, "inst_uuid": inst_uuid}] if 7 in ids else []),
    )
    collect_data = {"ok": True}
    format_data = {"add": [{"_id": 7, "inst_name": "host-a", "model_id": "host"}]}

    rewritten_collect, rewritten_format = normalize_collect_result_payloads(collect_data, format_data)

    assert rewritten_format["add"][0]["inst_uuid"] == inst_uuid
    assert rewritten_format["add"][0]["_id"] == 7
    assert rewritten_collect == {"ok": True}


def test_normalize_collect_result_payloads_keeps_unmapped_graph_id(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.InstanceManage.query_entity_by_ids",
        staticmethod(lambda _ids: []),
    )
    format_data = {"add": [{"_id": 7, "inst_name": "host-a", "model_id": "host"}]}

    rewritten = normalize_collect_result_payloads(format_data)

    assert rewritten[0]["add"][0]["_id"] == 7
    assert "inst_uuid" not in rewritten[0]["add"][0]


def test_normalize_collect_result_payloads_raises_when_lookup_fails(monkeypatch, caplog):
    from apps.cmdb.services.collect_snapshot_uuid import CollectSnapshotUuidLookupError

    secret = "SENTINEL_COLLECT_PAYLOAD"

    def boom(_ids):
        raise RuntimeError(f"graph lookup leaked {secret}")

    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.InstanceManage.query_entity_by_ids",
        staticmethod(boom),
    )
    collect_data = {"raw": secret}
    format_data = {"add": [{"_id": 7, "inst_name": "host-a"}]}

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        try:
            normalize_collect_result_payloads(collect_data, format_data)
        except CollectSnapshotUuidLookupError as exc:
            assert str(exc) == "graph_uuid_lookup"
        else:
            raise AssertionError("查图失败必须拒绝落库")

    records = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=collect_snapshot_uuid_skipped failed_stage=%s error_type=%s"
    assert record.args == ("graph_uuid_lookup", "RuntimeError")
    assert record.getMessage() == ("event=collect_snapshot_uuid_skipped failed_stage=graph_uuid_lookup error_type=RuntimeError")
    assert secret not in record.getMessage()
    assert record.exc_info is None
