from uuid import uuid4

import pytest

from apps.cmdb.models.change_record import CREATE_INST, ORDINARY_ATTRIBUTE_CHANGE, ChangeRecord
from apps.cmdb.utils.change_record import batch_create_change_record, create_change_record

pytestmark = pytest.mark.django_db


def test_create_change_record_writes_inst_uuid_from_after_data():
    inst_uuid = str(uuid4())
    record = create_change_record(
        inst_id=101,
        model_id="host",
        label="instance",
        _type=CREATE_INST,
        after_data={"_id": 101, "inst_uuid": inst_uuid, "inst_name": "h1"},
        operator="tester",
        scenario=ORDINARY_ATTRIBUTE_CHANGE,
    )

    record.refresh_from_db()
    assert str(record.inst_uuid) == inst_uuid
    assert record.inst_id == 101


def test_batch_create_change_record_defaults_inst_uuid_from_payload():
    inst_uuid = str(uuid4())
    batch_create_change_record(
        "instance",
        CREATE_INST,
        [
            {
                "inst_id": 202,
                "model_id": "host",
                "after_data": {"_id": 202, "inst_uuid": inst_uuid},
            }
        ],
        operator="tester",
    )

    record = ChangeRecord.objects.get(inst_id=202)
    assert str(record.inst_uuid) == inst_uuid


def test_batch_instance_change_record_captures_attribute_snapshot(monkeypatch):
    snapshot = {"version": 1, "attributes": {"disks": {"attr_type": "table"}}}
    captured = []
    monkeypatch.setattr(
        "apps.cmdb.services.change_record_snapshot.load_attribute_snapshot",
        lambda model_id, attr_ids: captured.append((model_id, set(attr_ids))) or snapshot,
    )

    batch_create_change_record(
        "instance",
        CREATE_INST,
        [{"inst_id": 303, "model_id": "host", "after_data": {"_id": 303, "disks": [{"name": "C:"}]}}],
    )

    record = ChangeRecord.objects.get(inst_id=303)
    assert captured == [("host", {"disks"})]
    assert record.attribute_snapshot == snapshot


def test_single_instance_change_record_captures_attribute_snapshot(monkeypatch):
    snapshot = {"version": 1, "attributes": {"interfaces": {"attr_type": "table"}}}
    captured = []
    monkeypatch.setattr(
        "apps.cmdb.services.change_record_snapshot.load_attribute_snapshot",
        lambda model_id, attr_ids: captured.append((model_id, set(attr_ids))) or snapshot,
    )

    record = create_change_record(
        inst_id=404,
        model_id="host",
        label="instance",
        _type=CREATE_INST,
        after_data={"_id": 404, "interfaces": [{"name": "eth0"}]},
    )

    assert captured == [("host", {"interfaces"})]
    assert record.attribute_snapshot == snapshot
