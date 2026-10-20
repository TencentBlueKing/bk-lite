from apps.node_mgmt.services.module_push_contract import (
    IngestResult,
    actor_scope_with_instance_orgs,
    ingest_auth_kwargs,
    org_ids_from_values,
    validate_envelope,
)


def test_validate_envelope_requires_source_and_event():
    ok, err = validate_envelope(
        {
            "source_module": "node_mgmt",
            "source_id": "node-1",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.0.0.1"},
            "link_ids": {"node_id": "node-1"},
        }
    )
    assert ok is True
    assert err is None


def test_validate_envelope_rejects_missing_source_id():
    ok, err = validate_envelope(
        {
            "source_module": "node_mgmt",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {},
            "link_ids": {},
        }
    )
    assert ok is False


def test_ingest_result_shape():
    r = IngestResult(id="abc", created=True, updated=False, ignored=False, conflict=None, skipped=False)
    assert r.as_dict()["id"] == "abc"
    assert r.as_dict()["skipped"] is False


def test_ingest_auth_kwargs_forwards_user_info():
    out = ingest_auth_kwargs(
        {
            "allowed_org_ids": [7],
            "operator": "alice",
            "user_info": {"user": "alice", "domain": "domain.com", "team": 7, "include_children": False},
        }
    )
    assert out["allowed_org_ids"] == [7]
    assert out["operator"] == "alice"
    assert out["user_info"]["team"] == 7


def test_ingest_auth_kwargs_omits_empty_user_info():
    assert ingest_auth_kwargs({"allowed_org_ids": [1], "operator": "bob", "user_info": {}}) == {
        "allowed_org_ids": [1],
        "operator": "bob",
    }


def test_org_ids_from_values_skips_invalid_and_dedupes():
    assert org_ids_from_values(["1", 2, "x", None, 2, "2"]) == [1, 2]
    assert org_ids_from_values(None) == []
    assert org_ids_from_values(3) == [3]


def test_actor_scope_with_instance_orgs_fills_only_when_empty():
    filled = actor_scope_with_instance_orgs({"operator": "alice"}, [9, "9"])
    assert filled["allowed_org_ids"] == [9]
    assert filled["operator"] == "alice"
    kept = actor_scope_with_instance_orgs({"allowed_org_ids": [1], "operator": "alice"}, [9])
    assert kept["allowed_org_ids"] == [1]
