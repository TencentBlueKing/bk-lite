import logging

from apps.cmdb.services.change_record_snapshot import build_attribute_snapshot, load_attribute_snapshot


def test_build_attribute_snapshot_only_keeps_audit_shape_for_touched_fields():
    attributes = [
        {
            "attr_id": "interfaces",
            "attr_name": "网卡",
            "attr_type": "table",
            "editable": True,
            "option": [
                {
                    "column_id": "mac",
                    "column_name": "MAC",
                    "column_type": "str",
                    "order": 1,
                    "is_row_key": True,
                    "unexpected": "discard-me",
                }
            ],
        },
        {"attr_id": "owner", "attr_name": "负责人", "attr_type": "str"},
    ]

    snapshot = build_attribute_snapshot(attributes, {"interfaces"})

    assert snapshot == {
        "version": 1,
        "attributes": {
            "interfaces": {
                "attr_id": "interfaces",
                "attr_name": "网卡",
                "attr_type": "table",
                "columns": [
                    {
                        "column_id": "mac",
                        "column_name": "MAC",
                        "column_type": "str",
                        "order": 1,
                        "is_row_key": True,
                    }
                ],
            }
        },
    }


def test_load_attribute_snapshot_failure_owns_safe_traceback(monkeypatch, caplog):
    sensitive_sentinel = "SECRET_ATTRIBUTE_RESPONSE_BODY"
    original_error = RuntimeError(sensitive_sentinel)

    def fail_search(_model_id):
        raise original_error

    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr", fail_search)

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        result = load_attribute_snapshot("host", {"interfaces"})

    assert result == {}
    records = [record for record in caplog.records if record.msg.startswith("event=cmdb_change_record_snapshot_failed")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=cmdb_change_record_snapshot_failed model_id=%s failed_stage=%s error_type=%s"
    assert record.args == ("host", "load_attributes", "RuntimeError")
    assert record.getMessage() == ("event=cmdb_change_record_snapshot_failed model_id=host " "failed_stage=load_attributes error_type=RuntimeError")
    assert record.exc_info is not None
    assert record.exc_info[2] is original_error.__traceback__
    assert record.exc_info[1] is not original_error
    assert original_error.args == (sensitive_sentinel,)
    assert sensitive_sentinel not in caplog.text
