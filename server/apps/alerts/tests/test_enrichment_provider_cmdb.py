import logging
from unittest.mock import MagicMock, patch

from apps.alerts.enrichment.keys import build_binding_key
from apps.alerts.enrichment.providers.cmdb import CMDBProvider

U1 = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
U2 = "c28e467a-501d-426f-a3c3-6e560c7b33cb"
NON_UUID = "host-10.10.24.62-SENTINEL"
UUID_V1 = "123e4567-e89b-12d3-a456-426614174000"


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_groups_by_model_and_batches_uuids(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {
        U1: {"owner": "alice"},
        U2: {"owner": "bob"},
    }
    k1 = build_binding_key({"model_id": "host", "inst_uuid": U1})
    k2 = build_binding_key({"model_id": "host", "inst_uuid": U2})
    out = CMDBProvider().fetch_batch([k1, k2], {"_authorized_team_ids": [7]})
    assert inst.search_instances_batch.call_count == 1
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": [U1, U2],
            "organization_ids": [7],
        },
        _timeout=3,
    )
    assert out[k1] == [{"owner": "alice"}]
    assert out[k2] == [{"owner": "bob"}]


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_miss_returns_empty_list(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {}
    k = build_binding_key({"model_id": "host", "inst_uuid": U1})
    out = CMDBProvider().fetch_batch([k], {"_authorized_team_ids": [7]})
    assert out[k] == []


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_marks_failed_keys_instead_of_real_miss(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = TimeoutError("rpc timeout")
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert result.records[key] == []
    assert result.failed_keys == {key}
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": [U1],
            "organization_ids": [7],
        },
        _timeout=3,
    )


@patch("apps.alerts.enrichment.providers.cmdb.monotonic", return_value=10.0)
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_does_not_start_group_after_deadline(mock_cmdb_cls, _mock_clock):
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_deadline_at": 9.0},
    )

    assert result.failed_keys == {key}
    assert result.budget_exhausted_keys == {key}
    mock_cmdb_cls.return_value.search_instances_batch.assert_not_called()


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_skips_non_uuid_without_failing_valid_keys(mock_cmdb_cls, caplog):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {U1: {"owner": "alice"}}
    good = build_binding_key({"model_id": "host", "inst_uuid": U1.upper()})
    bad = build_binding_key({"model_id": "host", "inst_uuid": NON_UUID})
    version = build_binding_key({"model_id": "host", "inst_uuid": UUID_V1})

    with caplog.at_level(logging.WARNING, logger="alert"):
        out = CMDBProvider().fetch_batch([good, bad, version], {"_authorized_team_ids": [7]})

    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": [U1],
            "organization_ids": [7],
        },
        _timeout=3,
    )
    assert out[good] == [{"owner": "alice"}]
    assert out[bad] == []
    assert out[version] == []
    assert not hasattr(out, "failed_keys")
    warning = next(record for record in caplog.records if record.name == "alert" and record.levelno == logging.WARNING)
    assert warning.msg == "[Enrichment] CMDB 跳过非 UUIDv4 定位 skipped=%s"
    assert warning.args == (2,)
    assert warning.getMessage() == "[Enrichment] CMDB 跳过非 UUIDv4 定位 skipped=2"
    assert warning.exc_info is None
    assert NON_UUID not in warning.getMessage()
    assert UUID_V1 not in warning.getMessage()
    assert not any(record.name == "apps.core.exceptions.base_app_exception" for record in caplog.records)


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_does_not_query_when_every_uuid_is_invalid(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    bad = build_binding_key({"model_id": "host", "inst_uuid": NON_UUID})

    out = CMDBProvider().fetch_batch([bad], {"_authorized_team_ids": [7]})

    inst.search_instances_batch.assert_not_called()
    assert out[bad] == []
