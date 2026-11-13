from datetime import datetime

from apps.system_mgmt.services.account_association_migration import plan_account_associations


def _channel(channel_id, **overrides):
    row = {
        "id": channel_id,
        "integration_instance_id": 7,
        "name": f"渠道{channel_id}",
        "platform_match_field": "email",
        "external_match_field": "email",
        "external_receive_field": "user_id",
        "schedule_config": {"enabled": False},
    }
    row.update(overrides)
    return row


def test_same_fields_stay_separate_and_each_keeps_its_own_result():
    planned = plan_account_associations(
        [
            _channel(5, name="较新", schedule_config={"enabled": True, "sync_time": "09:00"}),
            _channel(2, name="较早"),
            _channel(9, name="手机", platform_match_field="phone", external_match_field="mobile"),
        ],
        [
            {"id": 11, "channel_id": 2, "status": "success", "finished_at": datetime(2026, 11, 1)},
            {"id": 12, "channel_id": 5, "status": "partial", "finished_at": datetime(2026, 11, 5)},
            {"id": 13, "channel_id": 5, "status": "failed", "finished_at": datetime(2026, 11, 6)},
        ],
        {2: [101], 5: [201, 202], 9: [301]},
    )
    by_name = {item["name"]: item for item in planned}

    earlier = by_name["较早"]
    assert earlier["source_channel_ids"] == [2]
    assert earlier["kept_mapping_ids"] == [101]
    assert earlier["status"] == "ready"
    assert earlier["run_ids"] == [11]
    assert earlier["schedule_config"] == {"enabled": False}

    newer = by_name["较新"]
    assert newer["source_channel_ids"] == [5]
    assert newer["kept_mapping_ids"] == [201, 202]
    assert newer["status"] == "ready"
    assert newer["run_ids"] == [12, 13]
    assert newer["schedule_config"] == {"enabled": True, "sync_time": "09:00"}

    phone_plan = by_name["手机"]
    assert phone_plan["source_channel_ids"] == [9]
    assert phone_plan["kept_mapping_ids"] == []
    assert phone_plan["status"] == "pending_sync"
    assert phone_plan["schedule_config"] == {"enabled": False}


def test_failure_only_does_not_keep_mappings():
    planned = plan_account_associations(
        [_channel(4, name="只有失败")],
        [{"id": 20, "channel_id": 4, "status": "failed", "finished_at": datetime(2026, 11, 2)}],
        {4: [88]},
    )
    assert planned[0]["kept_mapping_ids"] == []
    assert planned[0]["status"] == "pending_sync"
    assert planned[0]["run_ids"] == [20]


def test_complete_success_with_no_mappings_stays_unusable():
    planned = plan_account_associations(
        [_channel(3)],
        [{"id": 7, "channel_id": 3, "status": "success", "finished_at": datetime(2026, 11, 3)}],
        {3: []},
    )
    assert planned[0]["status"] == "needs_resync"
    assert planned[0]["kept_mapping_ids"] == []


def test_each_channel_keeps_its_own_schedule():
    planned = plan_account_associations(
        [
            _channel(8, schedule_config={"enabled": False}),
            _channel(4, schedule_config={"enabled": True, "sync_time": "08:00"}),
            _channel(3, schedule_config={"enabled": True, "sync_time": "01:00"}),
        ],
        [],
        {},
    )
    by_name = {item["name"]: item for item in planned}
    assert by_name["渠道3"]["schedule_config"] == {"enabled": True, "sync_time": "01:00"}
    assert by_name["渠道4"]["schedule_config"] == {"enabled": True, "sync_time": "08:00"}
    assert by_name["渠道8"]["schedule_config"] == {"enabled": False}
