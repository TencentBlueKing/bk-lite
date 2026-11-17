import logging
from unittest.mock import MagicMock, patch

from apps.alerts.enrichment.keys import build_binding_key
from apps.alerts.enrichment.providers.cmdb import CMDBProvider, ci_context_scopes_from_projection

U1 = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
U2 = "c28e467a-501d-426f-a3c3-6e560c7b33cb"
NON_UUID = "host-10.10.24.62-SENTINEL"
UUID_V1 = "123e4567-e89b-12d3-a456-426614174000"


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_uses_in_process_cmdb_client(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {U1: {"owner": "alice"}}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    mock_cmdb_cls.assert_called_once_with(is_local_client=True)


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
def test_fetch_batch_maps_monitor_object_name_to_cmdb_model(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {U1: {"ip_addr": "10.11.27.147"}}
    key = build_binding_key({"model_id": "Host", "inst_uuid": U1})

    out = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [1]})

    assert out[key] == [{"ip_addr": "10.11.27.147"}]
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": [U1],
            "organization_ids": [1],
        },
        _timeout=3,
    )


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


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_uses_cmdb_uuid_without_model_and_stops(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {U1: {"owner": "alice"}}
    key = build_binding_key({"inst_uuid": U1, "monitor_id": "0001"})

    out = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert out[key] == [{"owner": "alice"}]
    inst.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "inst_uuids": [U1],
            "organization_ids": [7],
        },
        _timeout=3,
    )


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_falls_back_to_monitor_id_when_uuid_misses(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst

    def search(*, params, _timeout):
        if "inst_uuids" in params:
            return {}
        assert params["monitor_ids"] == ["0001"]
        assert "model_id" not in params
        return {"0001": {"owner": "ops"}}

    inst.search_instances_batch.side_effect = search
    key = build_binding_key({"inst_uuid": U1, "monitor_id": "0001"})

    out = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert out[key] == [{"owner": "ops"}]
    assert inst.search_instances_batch.call_count == 2


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_uuid_failure_does_not_query_monitor_id(mock_cmdb_cls):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = TimeoutError("rpc timeout")
    key = build_binding_key({"inst_uuid": U1, "monitor_id": "0001"})

    result = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    assert result.failed_keys == {key}
    inst.search_instances_batch.assert_called_once()


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


def test_ci_context_scopes_from_projection():
    assert ci_context_scopes_from_projection([{"source": "owner"}]) == []
    assert ci_context_scopes_from_projection([{"source": "application.inst_name"}]) == ["application"]
    assert ci_context_scopes_from_projection([{"source": "system.operator"}]) == ["system"]
    assert ci_context_scopes_from_projection([{"source": "application.operator"}, {"source": "system.inst_name"}]) == ["application", "system"]


APP = "a11a1111-b6bb-43cc-9eae-8eb8a09f795e"
SYS = "b22b2222-b6bb-43cc-9eae-8eb8a09f795e"


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_skips_ci_context_when_projection_has_no_app_fields(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.return_value = {U1: {"owner": "alice", "inst_uuid": U1}}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    out = CMDBProvider().fetch_batch([key], {"_authorized_team_ids": [7]})

    mock_lookup.assert_not_called()
    assert out[key] == [{"owner": "alice", "inst_uuid": U1}]
    assert inst.search_instances_batch.call_count == 1


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_overlays_application_fields_when_selected(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = [
        {U1: {"owner": "alice", "inst_uuid": U1, "ip_addr": "10.11.27.147"}},
        {APP: {"inst_name": "支付", "operator": 9, "app_id": "pay"}},
    ]
    mock_lookup.return_value = {U1: [{"root_uuid": APP, "system_uuid": SYS, "ci_uuid": U1}]}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    out = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["application"]},
    )

    mock_lookup.assert_called_once()
    assert mock_lookup.call_args.kwargs["inst_uuids"] == [U1]
    assert out[key][0]["owner"] == "alice"
    assert out[key][0]["application.inst_name"] == "支付"
    assert out[key][0]["application.operator"] == 9
    assert "system.inst_name" not in out[key][0]
    assert inst.search_instances_batch.call_count == 2
    inst.search_instances_batch.assert_any_call(
        params={
            "protocol_version": "2",
            "model_id": "application",
            "inst_uuids": [APP],
            "organization_ids": [7],
        },
        _timeout=3,
    )


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_overlays_system_fields_when_selected(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = [
        {U1: {"inst_uuid": U1}},
        {SYS: {"inst_name": "交易系统", "operator": 4}},
    ]
    mock_lookup.return_value = {U1: [{"root_uuid": APP, "system_uuid": SYS, "ci_uuid": U1}]}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    out = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["system"]},
    )

    assert out[key][0]["system.inst_name"] == "交易系统"
    assert out[key][0]["system.operator"] == 4
    assert "application.inst_name" not in out[key][0]
    inst.search_instances_batch.assert_any_call(
        params={
            "protocol_version": "2",
            "model_id": "system",
            "inst_uuids": [SYS],
            "organization_ids": [7],
        },
        _timeout=3,
    )


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_expands_records_for_multiple_applications(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    app_b = "c33c3333-b6bb-43cc-9eae-8eb8a09f795e"
    inst.search_instances_batch.side_effect = [
        {U1: {"inst_uuid": U1}},
        {APP: {"inst_name": "支付"}, app_b: {"inst_name": "账务"}},
    ]
    mock_lookup.return_value = {
        U1: [
            {"root_uuid": APP, "system_uuid": None, "ci_uuid": U1},
            {"root_uuid": app_b, "system_uuid": None, "ci_uuid": U1},
        ]
    }
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    out = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["application"]},
    )

    assert [row["application.inst_name"] for row in out[key]] == ["支付", "账务"]


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_overlays_application_and_system_fields(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = [
        {U1: {"inst_uuid": U1, "owner": "alice"}},
        {APP: {"inst_name": "支付", "app_id": "pay"}},
        {SYS: {"inst_name": "交易系统", "operator": 4}},
    ]
    mock_lookup.return_value = {U1: [{"root_uuid": APP, "system_uuid": SYS, "ci_uuid": U1}]}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    out = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["application", "system"]},
    )

    row = out[key][0]
    assert row["owner"] == "alice"
    assert row["application.inst_name"] == "支付"
    assert row["application.app_id"] == "pay"
    assert row["system.inst_name"] == "交易系统"
    assert row["system.operator"] == 4
    assert inst.search_instances_batch.call_count == 3


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_keeps_host_when_overlay_rpc_fails(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    host = {"owner": "alice", "inst_uuid": U1, "ip_addr": "10.11.27.147"}
    inst.search_instances_batch.side_effect = [
        {U1: host},
        TimeoutError("rpc timeout"),
    ]
    mock_lookup.return_value = {U1: [{"root_uuid": APP, "system_uuid": SYS, "ci_uuid": U1}]}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["application"]},
    )

    assert result.failed_keys == {key}
    assert result.records[key] == [host]
    assert "application.inst_name" not in result.records[key][0]


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_keeps_host_when_ci_context_lookup_fails(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    host = {"owner": "alice", "inst_uuid": U1}
    inst.search_instances_batch.return_value = {U1: host}
    mock_lookup.side_effect = RuntimeError("pg down")
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["application"]},
    )

    assert result.failed_keys == {key}
    assert result.records[key] == [host]
    assert inst.search_instances_batch.call_count == 1


@patch("apps.alerts.enrichment.providers.cmdb.monotonic")
@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_keeps_host_when_overlay_deadline_exhausted(mock_cmdb_cls, mock_lookup, mock_clock):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    host = {"owner": "alice", "inst_uuid": U1}
    clock = {"t": 10.0}

    def now():
        return clock["t"]

    def search(*, params, _timeout):
        clock["t"] = 20.0
        return {U1: host}

    mock_clock.side_effect = now
    inst.search_instances_batch.side_effect = search
    mock_lookup.return_value = {U1: [{"root_uuid": APP, "system_uuid": SYS, "ci_uuid": U1}]}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["application"], "_deadline_at": 15.0},
    )

    assert result.failed_keys == {key}
    assert result.budget_exhausted_keys == {key}
    assert result.records[key] == [host]
    mock_lookup.assert_not_called()


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_fetch_batch_keeps_host_and_application_when_system_overlay_fails(mock_cmdb_cls, mock_lookup):
    inst = MagicMock()
    mock_cmdb_cls.return_value = inst
    inst.search_instances_batch.side_effect = [
        {U1: {"owner": "alice", "inst_uuid": U1}},
        {APP: {"inst_name": "支付"}},
        TimeoutError("rpc timeout"),
    ]
    mock_lookup.return_value = {U1: [{"root_uuid": APP, "system_uuid": SYS, "ci_uuid": U1}]}
    key = build_binding_key({"model_id": "host", "inst_uuid": U1})

    result = CMDBProvider().fetch_batch(
        [key],
        {"_authorized_team_ids": [7], "_ci_context_scopes": ["application", "system"]},
    )

    assert result.failed_keys == {key}
    row = result.records[key][0]
    assert row["owner"] == "alice"
    assert row["application.inst_name"] == "支付"
    assert "system.inst_name" not in row
