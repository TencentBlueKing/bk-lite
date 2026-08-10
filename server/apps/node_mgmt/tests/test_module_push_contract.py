from apps.node_mgmt.services.module_push_contract import (
    IngestEnvelope,
    IngestResult,
    validate_envelope,
    LINK_CONFLICT,
)


def test_validate_envelope_requires_source_and_event():
    ok, err = validate_envelope({
        "source_module": "node_mgmt",
        "source_id": "node-1",
        "event_type": "upsert",
        "occurred_at": "2026-08-05T00:00:00Z",
        "raw": {"ip": "10.0.0.1"},
        "link_ids": {"node_id": "node-1"},
    })
    assert ok is True
    assert err is None


def test_validate_envelope_rejects_missing_source_id():
    ok, err = validate_envelope({
        "source_module": "node_mgmt",
        "event_type": "upsert",
        "occurred_at": "2026-08-05T00:00:00Z",
        "raw": {},
        "link_ids": {},
    })
    assert ok is False


def test_ingest_result_shape():
    r = IngestResult(id="abc", created=True, updated=False, ignored=False, conflict=None)
    assert r.as_dict()["id"] == "abc"
