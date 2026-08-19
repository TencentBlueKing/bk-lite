from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from django.core import signing
from django.test import override_settings

from apps.cmdb.nats import nats as cmdb_nats
from apps.cmdb.nats import list_instances_auth as auth

pytestmark = pytest.mark.unit


def _v2_params():
    return {
        "protocol_version": "2",
        "model_id": "host",
        "organization_ids": [1],
        "params": [{"field": "ip_addr", "type": "str=", "value": "10.0.0.1"}],
        "page": 2,
        "page_size": 10,
        "order": "-inst_name",
        "format": False,
    }


def _signed_params_with_claims(params, claims):
    signed = deepcopy(params)
    signed[auth.LIST_INSTANCES_AUTH_FIELD] = signing.dumps(
        claims,
        salt=auth.LIST_INSTANCES_SIGNING_SALT,
        compress=True,
    )
    return signed


def test_prepare_rpc_params_upgrades_v2_without_mutating_input():
    original = _v2_params()
    before = deepcopy(original)

    prepared = auth.prepare_list_instances_rpc_params(original)

    assert original == before
    assert prepared["protocol_version"] == "3"
    assert prepared[auth.LIST_INSTANCES_AUTH_FIELD]
    auth.authorize_list_instances_params(prepared)


def test_prepare_rpc_params_uses_nats_transport_json_semantics():
    original = {**_v2_params(), "params": [{"field": "created_at", "type": "datetime", "value": datetime(2026, 8, 19, tzinfo=timezone.utc)}]}

    prepared = auth.prepare_list_instances_rpc_params(original)

    assert prepared["params"][0]["value"] == "2026-08-19T00:00:00Z"
    auth.authorize_list_instances_params(prepared)


@pytest.mark.parametrize("auth_value", [None, "", "tampered-token"])
def test_v3_rejects_missing_or_tampered_auth(auth_value):
    params = {**_v2_params(), "protocol_version": "3"}
    if auth_value is not None:
        params[auth.LIST_INSTANCES_AUTH_FIELD] = auth_value

    with pytest.raises(ValueError, match="invalid or expired list_instances authorization"):
        auth.authorize_list_instances_params(params)


@pytest.mark.parametrize(
    ("claims_update", "signed_params_update"),
    [
        ({"aud": "other-service"}, {}),
        ({"op": "search_instances"}, {}),
        ({"params": {**_v2_params(), "protocol_version": "3", "page": 99}}, {}),
        ({}, {"page": 99}),
    ],
)
def test_v3_rejects_wrong_claims_or_params(claims_update, signed_params_update):
    params = {**_v2_params(), "protocol_version": "3"}
    claims = {
        "aud": auth.LIST_INSTANCES_AUDIENCE,
        "op": auth.LIST_INSTANCES_OPERATION,
        "params": deepcopy(params),
        **claims_update,
    }
    signed = _signed_params_with_claims(params, claims)
    signed.update(signed_params_update)

    with pytest.raises(ValueError, match="invalid or expired list_instances authorization"):
        auth.authorize_list_instances_params(signed)


def test_v3_rejects_expired_auth(monkeypatch):
    issued_at = 1_700_000_000
    monkeypatch.setattr(signing.time, "time", lambda: issued_at)
    prepared = auth.prepare_list_instances_rpc_params(_v2_params())
    monkeypatch.setattr(signing.time, "time", lambda: issued_at + auth.LIST_INSTANCES_AUTH_MAX_AGE_SECONDS + 1)

    with pytest.raises(ValueError, match="invalid or expired list_instances authorization"):
        auth.authorize_list_instances_params(prepared)


def test_v3_accepts_previous_secret_during_rotation():
    with override_settings(SECRET_KEY="old-secret", SECRET_KEY_FALLBACKS=[]):
        prepared = auth.prepare_list_instances_rpc_params(_v2_params())

    with override_settings(SECRET_KEY="new-secret", SECRET_KEY_FALLBACKS=["old-secret"]):
        auth.authorize_list_instances_params(prepared)


def test_legacy_v2_is_compatible_by_default_and_observation_is_bounded(monkeypatch):
    warning = Mock()
    now = [1000.0]
    monkeypatch.delenv(auth.LIST_INSTANCES_LEGACY_ENV, raising=False)
    monkeypatch.setattr(auth.logger, "warning", warning)
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(auth, "_legacy_next_observation_at", 0.0)

    auth.authorize_list_instances_params(_v2_params())
    auth.authorize_list_instances_params({**_v2_params(), "organization_ids": [987654321]})
    now[0] += auth.LIST_INSTANCES_LEGACY_OBSERVATION_INTERVAL_SECONDS + 1
    auth.authorize_list_instances_params(_v2_params())

    assert warning.call_count == 2
    logged = " ".join(str(part) for call in warning.call_args_list for part in (*call.args, *call.kwargs.values()))
    assert "organization_ids" not in logged
    assert "987654321" not in logged
    assert "_auth" not in logged


def test_legacy_v2_can_be_disabled(monkeypatch):
    monkeypatch.setenv(auth.LIST_INSTANCES_LEGACY_ENV, "false")

    with pytest.raises(ValueError, match="legacy list_instances protocol v2 is disabled"):
        auth.authorize_list_instances_params(_v2_params())


def test_unknown_protocol_is_rejected():
    with pytest.raises(ValueError, match="unsupported CMDB list_instances protocol version"):
        auth.authorize_list_instances_params({**_v2_params(), "protocol_version": "99"})


def test_handler_accepts_valid_v3_and_preserves_query_contract(monkeypatch):
    instance_list = Mock(return_value=([{"inst_uuid": "u1"}], 1))
    monkeypatch.setattr(cmdb_nats.InstanceManage, "instance_list", instance_list)
    prepared = auth.prepare_list_instances_rpc_params(_v2_params())

    result = cmdb_nats.list_instances(prepared)

    assert result == {"count": 1, "items": [{"inst_uuid": "u1"}]}
    instance_list.assert_called_once_with(
        model_id="host",
        params=[
            {"field": "ip_addr", "type": "str=", "value": "10.0.0.1"},
            {"field": "organization", "type": "list[]", "value": [1]},
        ],
        page=2,
        page_size=10,
        order="-inst_name",
        creator="",
        permission_map={},
    )


def test_repeated_valid_v3_query_is_read_only_and_repeatable(monkeypatch):
    instance_list = Mock(return_value=([{"inst_uuid": "u1"}], 1))
    monkeypatch.setattr(cmdb_nats.InstanceManage, "instance_list", instance_list)
    prepared = auth.prepare_list_instances_rpc_params(_v2_params())

    first = cmdb_nats.list_instances(prepared)
    second = cmdb_nats.list_instances(prepared)

    assert first == second == {"count": 1, "items": [{"inst_uuid": "u1"}]}
    assert instance_list.call_count == 2


@pytest.mark.parametrize("mutation", ["missing", "tampered", "expired", "audience", "operation", "params"])
def test_handler_rejects_invalid_v3_before_query(monkeypatch, mutation):
    instance_list = Mock(return_value=([], 0))
    monkeypatch.setattr(cmdb_nats.InstanceManage, "instance_list", instance_list)
    issued_at = 1_700_000_000
    monkeypatch.setattr(signing.time, "time", lambda: issued_at)
    unsigned = {**_v2_params(), "protocol_version": "3"}
    prepared = auth.prepare_list_instances_rpc_params(_v2_params())
    if mutation == "missing":
        prepared.pop(auth.LIST_INSTANCES_AUTH_FIELD)
    elif mutation == "tampered":
        prepared[auth.LIST_INSTANCES_AUTH_FIELD] += "x"
    elif mutation == "expired":
        monkeypatch.setattr(signing.time, "time", lambda: issued_at + auth.LIST_INSTANCES_AUTH_MAX_AGE_SECONDS + 1)
    elif mutation == "audience":
        prepared = _signed_params_with_claims(
            unsigned,
            {"aud": "other-service", "op": auth.LIST_INSTANCES_OPERATION, "params": unsigned},
        )
    elif mutation == "operation":
        prepared = _signed_params_with_claims(
            unsigned,
            {"aud": auth.LIST_INSTANCES_AUDIENCE, "op": "search_instances", "params": unsigned},
        )
    else:
        prepared["page"] = 99

    with pytest.raises(ValueError):
        cmdb_nats.list_instances(prepared)

    instance_list.assert_not_called()


def test_handler_legacy_v2_disabled_has_no_query_side_effect(monkeypatch):
    instance_list = Mock(return_value=([], 0))
    monkeypatch.setattr(cmdb_nats.InstanceManage, "instance_list", instance_list)
    monkeypatch.setenv(auth.LIST_INSTANCES_LEGACY_ENV, "false")

    with pytest.raises(ValueError, match="legacy list_instances protocol v2 is disabled"):
        cmdb_nats.list_instances(_v2_params())

    instance_list.assert_not_called()
