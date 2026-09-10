import json
import logging

from apps.cmdb.services.host_zombie_whitelist import HOST_ZOMBIE_WHITELIST_ATTR, ensure_host_zombie_whitelist_attr
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.monitored_host import build_monitored_host_row, normalize_zombie_whitelist
from apps.core.exceptions.base_app_exception import BaseAppException


def test_drop_host_without_monitor_id():
    assert build_monitored_host_row({"inst_uuid": "u1", "inst_name": "h1", "ip_addr": "10.0.0.1"}) is None


def test_drop_host_with_empty_monitor_id():
    assert build_monitored_host_row({"inst_uuid": "u1", "inst_name": "h1", "ip_addr": "10.0.0.1", "monitor_id": ""}) is None
    assert build_monitored_host_row({"inst_uuid": "u1", "inst_name": "h1", "ip_addr": "10.0.0.1", "monitor_id": "  "}) is None


def test_drop_host_without_inst_uuid():
    assert build_monitored_host_row({"inst_name": "h1", "ip_addr": "10.0.0.1", "monitor_id": "m-1"}) is None
    assert build_monitored_host_row({"inst_uuid": "", "inst_name": "h1", "ip_addr": "10.0.0.1", "monitor_id": "m-1"}) is None


def test_row_unwraps_os_type_enum_list():
    row = build_monitored_host_row(
        {
            "inst_uuid": "u1",
            "inst_name": "web-1",
            "ip_addr": "10.0.0.1",
            "os_type": ["1"],
            "monitor_id": "m-1",
        }
    )
    assert row["os_type"] == "1"
    assert row["os_type_label"] == "Linux"


def test_row_maps_os_and_empty_whitelist_as_no():
    row = build_monitored_host_row(
        {
            "inst_uuid": "u1",
            "inst_name": "web-1",
            "ip_addr": "10.0.0.1",
            "os_type": "1",
            "monitor_id": "m-1",
            "organization": [3],
        },
        org_names={3: "交易"},
    )
    assert row["os_type_label"] == "Linux"
    assert row["zombie_whitelist"] == "no"
    assert row["biz_name"] == "交易"
    assert row["display_name"] == "web-1 (10.0.0.1)"
    assert row["inst_uuid"] == "u1"
    assert row["monitor_id"] == "m-1"
    assert row["host_name"] == "web-1"
    assert row["ip"] == "10.0.0.1"
    assert row["os_type"] == "1"


def test_os_type_other_and_unknown_map_to_other():
    other = build_monitored_host_row(
        {
            "inst_uuid": "u2",
            "inst_name": "misc-1",
            "ip_addr": "10.0.0.2",
            "os_type": "other",
            "monitor_id": "m-2",
        }
    )
    unknown = build_monitored_host_row(
        {
            "inst_uuid": "u3",
            "inst_name": "misc-2",
            "ip_addr": "10.0.0.3",
            "os_type": "99",
            "monitor_id": "m-3",
        }
    )
    assert other["os_type_label"] == "Other"
    assert unknown["os_type_label"] == "Other"


def test_entity_whitelist_yes_stays_yes():
    row = build_monitored_host_row(
        {
            "inst_uuid": "u4",
            "inst_name": "web-2",
            "ip_addr": "10.0.0.4",
            "os_type": "2",
            "monitor_id": "m-4",
            "zombie_whitelist": "yes",
            "node_id": "n-4",
        }
    )
    assert row["zombie_whitelist"] == "yes"
    assert row["os_type_label"] == "Windows"
    assert row["node_id"] == "n-4"


def test_multi_org_names_joined_with_dunhao():
    row = build_monitored_host_row(
        {
            "inst_uuid": "u5",
            "inst_name": "web-3",
            "ip_addr": "10.0.0.5",
            "os_type": "1",
            "monitor_id": "m-5",
            "organization": [3, 8],
        },
        org_names={3: "交易", 8: "清算"},
    )
    assert row["biz_name"] == "交易、清算"


def test_missing_org_names_yield_empty_biz_name():
    row = build_monitored_host_row(
        {
            "inst_uuid": "u6",
            "inst_name": "web-4",
            "ip_addr": "10.0.0.6",
            "monitor_id": "m-6",
            "organization": [9],
        }
    )
    assert row["biz_name"] == ""


def test_whitelist_yes_only_when_enum_yes():
    assert normalize_zombie_whitelist("yes") == "yes"
    assert normalize_zombie_whitelist("") == "no"
    assert normalize_zombie_whitelist(None) == "no"
    assert normalize_zombie_whitelist(["yes"]) == "yes"
    assert normalize_zombie_whitelist(["no"]) == "no"
    assert normalize_zombie_whitelist([]) == "no"


def test_entity_whitelist_enum_list_yes_stays_yes():
    row = build_monitored_host_row(
        {
            "inst_uuid": "u",
            "zombie_whitelist": ["yes"],
            "monitor_id": "m-1",
        }
    )
    assert row["zombie_whitelist"] == "yes"


def _host_model(*, attrs):
    return {"_id": 1, "model_id": "host", "attrs": json.dumps(attrs)}


def _cmdb_event_records(caplog, event_prefix: str):
    return [record for record in caplog.records if record.name == "cmdb" and record.msg.startswith(event_prefix)]


def _assert_cmdb_info_event(record, *, template: str, args: tuple, rendered: str, secret: str):
    assert record.levelno == logging.INFO
    assert record.msg == template
    assert record.args == args
    assert record.getMessage() == rendered
    assert secret not in record.getMessage()
    assert secret not in "".join(str(arg) for arg in record.args)


def test_ensure_creates_editable_enum_not_system_link(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(attrs=[{"attr_id": "ip_addr", "attr_name": "内网IP"}]),
    )
    create = mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        return_value=dict(HOST_ZOMBIE_WHITELIST_ATTR),
    )
    update = mocker.patch("apps.cmdb.services.model.ModelManage.update_model_attr")

    assert ensure_host_zombie_whitelist_attr(username="tester") is True
    create.assert_called_once()
    update.assert_not_called()
    assert create.call_args.args[0] == "host"
    attr_info = create.call_args.args[1]
    assert attr_info["attr_id"] == "zombie_whitelist"
    assert attr_info["attr_type"] == "enum"
    assert attr_info["editable"] is True
    assert attr_info["is_required"] is False
    assert attr_info["option"] == [{"id": "yes", "name": "是"}, {"id": "no", "name": "否"}]
    assert attr_info.get("is_system_link") in (None, False)
    assert create.call_args.kwargs["username"] == "tester"


def test_ensure_ready_when_options_present(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(
            attrs=[
                {
                    "attr_id": "zombie_whitelist",
                    "attr_type": "enum",
                    "editable": True,
                    "option": [{"id": "yes", "name": "是"}, {"id": "no", "name": "否"}],
                }
            ]
        ),
    )
    create = mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")
    update = mocker.patch("apps.cmdb.services.model.ModelManage.update_model_attr")

    assert ensure_host_zombie_whitelist_attr() is True
    create.assert_not_called()
    update.assert_not_called()


def test_ensure_patches_missing_options(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(
            attrs=[
                {
                    "attr_id": "zombie_whitelist",
                    "attr_type": "enum",
                    "editable": True,
                    "option": [{"id": "no", "name": "否"}],
                }
            ]
        ),
    )
    create = mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")
    update = mocker.patch("apps.cmdb.services.model.ModelManage.update_model_attr")

    assert ensure_host_zombie_whitelist_attr(username="admin") is True
    create.assert_not_called()
    update.assert_called_once()
    patched = update.call_args.args[1]
    option_ids = {item["id"] for item in patched["option"]}
    assert option_ids == {"yes", "no"}
    assert patched.get("is_system_link") in (None, False)
    assert patched.get("editable") is True


def test_ensure_treats_duplicate_as_ready(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(attrs=[]),
    )
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        side_effect=BaseAppException("model attr repetition"),
    )

    assert ensure_host_zombie_whitelist_attr() is True


def test_ensure_patches_uneditable_system_link_flags(mocker, caplog):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(
            attrs=[
                {
                    "attr_id": "zombie_whitelist",
                    "attr_type": "enum",
                    "editable": False,
                    "is_system_link": True,
                    "option": [{"id": "yes", "name": "是"}, {"id": "no", "name": "否"}],
                }
            ]
        ),
    )
    create = mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")
    update = mocker.patch("apps.cmdb.services.model.ModelManage.update_model_attr")
    caplog.set_level(logging.INFO, logger="cmdb")
    secret = "super-secret-token"

    assert ensure_host_zombie_whitelist_attr(username="admin") is True
    create.assert_not_called()
    update.assert_called_once()
    patched = update.call_args.args[1]
    assert patched["editable"] is True
    assert patched["is_system_link"] is False
    assert patched["option"] == [{"id": "yes", "name": "是"}, {"id": "no", "name": "否"}]
    assert update.call_args.args[0] == "host"
    assert update.call_args.kwargs["username"] == "admin"
    records = _cmdb_event_records(caplog, "event=host_zombie_whitelist_option_patched")
    assert len(records) == 1
    _assert_cmdb_info_event(
        records[0],
        template="event=host_zombie_whitelist_option_patched model_id=%s attr_id=%s",
        args=("host", "zombie_whitelist"),
        rendered="event=host_zombie_whitelist_option_patched model_id=host attr_id=zombie_whitelist",
        secret=secret,
    )


def test_ensure_patches_flags_and_missing_options_in_one_update(mocker, caplog):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(
            attrs=[
                {
                    "attr_id": "zombie_whitelist",
                    "attr_type": "enum",
                    "editable": False,
                    "is_system_link": True,
                    "option": [{"id": "no", "name": "否"}],
                }
            ]
        ),
    )
    create = mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")
    update = mocker.patch("apps.cmdb.services.model.ModelManage.update_model_attr")
    caplog.set_level(logging.INFO, logger="cmdb")
    secret = "super-secret-token"

    assert ensure_host_zombie_whitelist_attr(username="admin") is True
    create.assert_not_called()
    update.assert_called_once()
    patched = update.call_args.args[1]
    assert patched["editable"] is True
    assert patched["is_system_link"] is False
    assert {item["id"] for item in patched["option"]} == {"yes", "no"}
    records = _cmdb_event_records(caplog, "event=host_zombie_whitelist_option_patched")
    assert len(records) == 1
    _assert_cmdb_info_event(
        records[0],
        template="event=host_zombie_whitelist_option_patched model_id=%s attr_id=%s",
        args=("host", "zombie_whitelist"),
        rendered="event=host_zombie_whitelist_option_patched model_id=host attr_id=zombie_whitelist",
        secret=secret,
    )


def test_ensure_logs_warning_when_host_model_missing(mocker, caplog):
    mocker.patch("apps.cmdb.services.model.ModelManage.search_model_info", return_value=None)
    caplog.set_level(logging.WARNING, logger="cmdb")
    secret = "super-secret-token"

    ready = ensure_host_zombie_whitelist_attr()

    assert ready is False
    records = _cmdb_event_records(caplog, "event=host_zombie_whitelist_ensure_skipped")
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.msg == ("event=host_zombie_whitelist_ensure_skipped model_id=%s attr_id=%s failed_stage=%s error_type=%s")
    assert record.args == ("host", "zombie_whitelist", "search_model_info", "ModelNotFound")
    rendered = record.getMessage()
    assert rendered == (
        "event=host_zombie_whitelist_ensure_skipped model_id=host attr_id=zombie_whitelist " "failed_stage=search_model_info error_type=ModelNotFound"
    )
    assert secret not in rendered
    assert secret not in "".join(str(arg) for arg in record.args)


def test_ensure_logs_info_when_option_patched(mocker, caplog):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(
            attrs=[
                {
                    "attr_id": "zombie_whitelist",
                    "attr_type": "enum",
                    "editable": True,
                    "option": [{"id": "no", "name": "否"}],
                }
            ]
        ),
    )
    mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")
    mocker.patch("apps.cmdb.services.model.ModelManage.update_model_attr")
    caplog.set_level(logging.INFO, logger="cmdb")
    secret = "super-secret-token"

    assert ensure_host_zombie_whitelist_attr() is True

    records = _cmdb_event_records(caplog, "event=host_zombie_whitelist_option_patched")
    assert len(records) == 1
    _assert_cmdb_info_event(
        records[0],
        template="event=host_zombie_whitelist_option_patched model_id=%s attr_id=%s",
        args=("host", "zombie_whitelist"),
        rendered="event=host_zombie_whitelist_option_patched model_id=host attr_id=zombie_whitelist",
        secret=secret,
    )


def test_ensure_logs_info_when_duplicate_treated_as_ready(mocker, caplog):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(attrs=[]),
    )
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        side_effect=BaseAppException("model attr repetition"),
    )
    caplog.set_level(logging.INFO, logger="cmdb")
    secret = "super-secret-token"

    assert ensure_host_zombie_whitelist_attr() is True

    records = _cmdb_event_records(caplog, "event=host_zombie_whitelist_attr_ready")
    assert len(records) == 1
    _assert_cmdb_info_event(
        records[0],
        template="event=host_zombie_whitelist_attr_ready model_id=%s attr_id=%s",
        args=("host", "zombie_whitelist"),
        rendered="event=host_zombie_whitelist_attr_ready model_id=host attr_id=zombie_whitelist",
        secret=secret,
    )


def test_ensure_logs_info_when_attr_created(mocker, caplog):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=_host_model(attrs=[{"attr_id": "ip_addr", "attr_name": "内网IP"}]),
    )
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        return_value=dict(HOST_ZOMBIE_WHITELIST_ATTR),
    )
    mocker.patch("apps.cmdb.services.model.ModelManage.update_model_attr")
    caplog.set_level(logging.INFO, logger="cmdb")
    secret = "super-secret-token"

    assert ensure_host_zombie_whitelist_attr() is True

    records = _cmdb_event_records(caplog, "event=host_zombie_whitelist_attr_created")
    assert len(records) == 1
    _assert_cmdb_info_event(
        records[0],
        template="event=host_zombie_whitelist_attr_created model_id=%s attr_id=%s",
        args=("host", "zombie_whitelist"),
        rendered="event=host_zombie_whitelist_attr_created model_id=host attr_id=zombie_whitelist",
        secret=secret,
    )


def test_post_import_extras_ensures_host_zombie_whitelist(mocker):
    fake = mocker.MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    mocker.patch("apps.cmdb.services.model.GraphClient", return_value=fake)
    mocker.patch.object(ModelManage, "_import_auto_relation_rule_sets_from_asso_sheets")
    mocker.patch("apps.cmdb.services.module_ingest.ensure_model_node_id_attr")
    mocker.patch("apps.cmdb.services.module_ingest.ensure_model_monitor_id_attr")
    ensure = mocker.patch(
        "apps.cmdb.services.host_zombie_whitelist.ensure_host_zombie_whitelist_attr",
        return_value=True,
    )

    ModelManage._apply_model_config_post_import_extras({})

    ensure.assert_called_once_with(username="admin")
