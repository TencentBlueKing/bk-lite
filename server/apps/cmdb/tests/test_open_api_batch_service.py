import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.cmdb.graph.falkordb import FalkorDBClient
from apps.cmdb.services.instance import InstanceManage, _require_complete_batch_instances
from apps.cmdb.services.unique_rule import ModelUniqueRule
from apps.core.exceptions.base_app_exception import BaseAppException


pytestmark = pytest.mark.unit


class _NoopExtension:
    def normalize_file_fields(self, model_id, instance_data, attrs, *, operator, old_instance=None):
        return instance_data

    def commit_instance_files(self, model_id, inst_id, saved, attrs, *, operator):
        return None

    def on_instances_delete(self, inst_ids):
        return None


def _use_real_required_validator(graph):
    graph.check_required_attr.side_effect = (
        lambda item, check_attr_map: FalkorDBClient.check_required_attr(
            graph,
            item,
            check_attr_map,
        )
    )


@patch("apps.cmdb.services.instance.GraphClient")
@patch("apps.cmdb.services.instance.ModelManage.search_model_attr")
@patch("apps.cmdb.services.instance.build_unique_rule_context")
def test_batch_create_rolls_back_graph_when_one_item_fails(mock_unique_rules, mock_attrs, mock_graph):
    mock_unique_rules.return_value.unique_rules = []
    mock_unique_rules.return_value.attrs_by_id = {}
    mock_attrs.return_value = [
        {
            "attr_id": "inst_name",
            "attr_name": "名称",
            "is_required": True,
            "is_only": True,
        }
    ]
    graph = mock_graph.return_value.__enter__.return_value
    graph.query_entity.return_value = ([], 0)
    graph.batch_create_entity.return_value = [
        {
            "success": True,
            "data": {"_id": 1, "model_id": "host", "inst_name": "h1"},
        },
        {
            "success": False,
            "data": {"model_id": "host", "inst_name": "h2"},
            "message": "graph write failed",
        },
    ]

    with pytest.raises(BaseAppException, match="graph write failed"):
        InstanceManage.instance_batch_create(
            "host",
            [{"inst_name": "h1"}, {"inst_name": "h2"}],
            "api-user",
            [7],
        )

    graph.batch_delete_entity.assert_called_once_with("instance", [1])


@patch("apps.cmdb.services.instance.GraphClient")
@patch("apps.cmdb.services.instance.ModelManage.search_model_attr")
@patch("apps.cmdb.services.instance.build_unique_rule_context")
def test_batch_create_preserves_original_error_when_cleanup_fails(
    mock_unique_rules,
    mock_attrs,
    mock_graph,
    caplog,
):
    mock_unique_rules.return_value.unique_rules = []
    mock_unique_rules.return_value.attrs_by_id = {}
    mock_attrs.return_value = []
    graph = mock_graph.return_value.__enter__.return_value
    graph.query_entity.return_value = ([], 0)
    graph.batch_create_entity.return_value = [
        {
            "success": True,
            "data": {"_id": 1, "model_id": "host", "inst_name": "api_password=secret"},
        },
        {
            "success": False,
            "data": {"model_id": "host", "inst_name": "h2"},
            "message": "original graph failure",
        },
    ]
    graph.batch_delete_entity.side_effect = RuntimeError("cleanup secret=do-not-log")

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        with pytest.raises(BaseAppException, match="original graph failure"):
            InstanceManage.instance_batch_create(
                "host",
                [{"inst_name": "h1"}, {"inst_name": "h2"}],
                "api-user",
                [7],
            )

    assert "cleanup_ids=[1]" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "error_summary=cleanup_failed" in caplog.text
    assert "api_password" not in caplog.text
    assert "do-not-log" not in caplog.text


@patch("apps.cmdb.services.instance.GraphClient")
@patch("apps.cmdb.services.instance.ModelManage.search_model_attr")
@patch("apps.cmdb.services.instance.build_unique_rule_context")
def test_batch_create_reports_preprocessing_failure_index_before_graph_write(
    mock_unique_rules,
    mock_attrs,
    mock_graph,
):
    mock_unique_rules.return_value.unique_rules = []
    mock_unique_rules.return_value.attrs_by_id = {}
    mock_attrs.return_value = []

    def validate_enum(item, attrs):
        if item["inst_name"] == "bad":
            raise BaseAppException("枚举值非法")
        return item

    with patch("apps.cmdb.services.instance.apply_enum_validation_for_instance", side_effect=validate_enum):
        with pytest.raises(BaseAppException, match="请求参数非法") as exc_info:
            InstanceManage.instance_batch_create(
                "host",
                [{"inst_name": "ok"}, {"inst_name": "bad"}],
                "api-user",
                [7],
            )

    assert getattr(exc_info.value, "index", None) == 1
    mock_graph.return_value.__enter__.return_value.batch_create_entity.assert_not_called()


@pytest.mark.parametrize(
    "invalid_item",
    [
        {"port": 81},
        {"inst_name": "h2", "port": 70000},
    ],
)
def test_batch_create_prevalidates_required_and_field_type_before_graph_write(invalid_item):
    attrs = [
        {
            "attr_id": "inst_name",
            "attr_name": "名称",
            "attr_type": "str",
            "is_required": True,
            "option": {},
        },
        {
            "attr_id": "port",
            "attr_name": "端口",
            "attr_type": "int",
            "option": {"min_value": 1, "max_value": 65535},
        },
    ]
    context = SimpleNamespace(unique_rules=[], attrs_by_id={item["attr_id"]: item for item in attrs})
    with (
        patch("apps.cmdb.services.instance.ModelManage.search_model_attr", return_value=attrs),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension", return_value=_NoopExtension()),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        graph = mock_graph.return_value.__enter__.return_value
        graph.query_entity.return_value = ([], 0)
        _use_real_required_validator(graph)

        with pytest.raises(BaseAppException) as exc_info:
            InstanceManage.instance_batch_create(
                "host",
                [{"inst_name": "h1", "port": 80}, invalid_item],
                "api-user",
                [7],
            )

    assert getattr(exc_info.value, "reason", None) == "validation"
    assert getattr(exc_info.value, "index", None) == 1
    graph.batch_create_entity.assert_not_called()


def test_batch_create_does_not_persist_free_tags_when_later_item_is_invalid():
    attrs = [
        {
            "attr_id": "inst_name",
            "attr_name": "名称",
            "attr_type": "str",
            "is_required": True,
            "option": {},
        },
        {"attr_id": "tag", "attr_name": "标签", "attr_type": "tag", "option": {"mode": "free"}},
    ]
    context = SimpleNamespace(unique_rules=[], attrs_by_id={item["attr_id"]: item for item in attrs})
    with (
        patch("apps.cmdb.services.instance.ModelManage.search_model_attr", return_value=attrs),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.instance.ModelManage.merge_tag_options_from_values") as mock_merge_tags,
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension", return_value=_NoopExtension()),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        graph = mock_graph.return_value.__enter__.return_value
        graph.query_entity.return_value = ([], 0)
        _use_real_required_validator(graph)

        with pytest.raises(BaseAppException) as exc_info:
            InstanceManage.instance_batch_create(
                "host",
                [{"inst_name": "h1", "tag": ["env:prod"]}, {"tag": ["team:ops"]}],
                "api-user",
                [7],
            )

    assert getattr(exc_info.value, "index", None) == 1
    mock_merge_tags.assert_not_called()
    graph.batch_create_entity.assert_not_called()


def test_batch_create_persists_all_free_tags_once_after_prevalidation():
    attrs = [
        {
            "attr_id": "inst_name",
            "attr_name": "名称",
            "attr_type": "str",
            "is_required": True,
            "option": {},
        },
        {"attr_id": "tag", "attr_name": "标签", "attr_type": "tag", "option": {"mode": "free"}},
    ]
    context = SimpleNamespace(unique_rules=[], attrs_by_id={item["attr_id"]: item for item in attrs})
    events = []
    with (
        patch("apps.cmdb.services.instance.ModelManage.search_model_attr", return_value=attrs),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.instance.ModelManage.merge_tag_options_from_values") as mock_merge_tags,
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension", return_value=_NoopExtension()),
        patch("apps.cmdb.services.instance.batch_create_change_record"),
        patch("apps.cmdb.services.instance.schedule_instance_auto_relation_reconcile"),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        graph = mock_graph.return_value.__enter__.return_value
        graph.query_entity.return_value = ([], 0)
        _use_real_required_validator(graph)
        mock_merge_tags.side_effect = lambda *args: events.append("merge_tags")
        graph.batch_create_entity.side_effect = lambda *args: events.append("graph_write") or [
            {"success": True, "data": {"_id": 1, "model_id": "host", "inst_name": "h1"}},
            {"success": True, "data": {"_id": 2, "model_id": "host", "inst_name": "h2"}},
        ]

        InstanceManage.instance_batch_create(
            "host",
            [
                {"inst_name": "h1", "tag": ["env:prod"]},
                {"inst_name": "h2", "tag": ["team:ops"]},
            ],
            "api-user",
            [7],
        )

    mock_merge_tags.assert_called_once_with("host", ["env:prod", "team:ops"])
    assert events == ["merge_tags", "graph_write"]


@pytest.mark.parametrize(
    ("attrs", "unique_rules", "items", "expected_field"),
    [
        (
            [{"attr_id": "serial", "attr_name": "序列号", "is_only": True}],
            [],
            [{"serial": "same"}, {"serial": "same"}],
            "serial",
        ),
        (
            [
                {"attr_id": "region", "attr_name": "区域"},
                {"attr_id": "code", "attr_name": "编码"},
            ],
            [ModelUniqueRule(rule_id="region-code", order=1, field_ids=["region", "code"])],
            [
                {"region": "cn", "code": "001"},
                {"region": "cn", "code": "001"},
            ],
            "region",
        ),
    ],
)
def test_batch_create_rejects_in_batch_unique_conflict_before_graph_write(
    attrs,
    unique_rules,
    items,
    expected_field,
):
    attrs_by_id = {item["attr_id"]: item for item in attrs}
    context = SimpleNamespace(unique_rules=unique_rules, attrs_by_id=attrs_by_id)
    with (
        patch("apps.cmdb.services.instance.ModelManage.search_model_attr", return_value=attrs),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        graph = mock_graph.return_value.__enter__.return_value
        graph.query_entity.return_value = ([], 0)
        with pytest.raises(BaseAppException) as exc_info:
            InstanceManage.instance_batch_create("host", items, "api-user", [7])

    assert getattr(exc_info.value, "index", None) == 1
    assert getattr(exc_info.value, "reason", None) == "unique_conflict"
    assert getattr(exc_info.value, "field", None) == expected_field
    graph.batch_create_entity.assert_not_called()


def test_batch_create_rejects_in_batch_subnet_overlap_before_graph_write():
    context = SimpleNamespace(unique_rules=[], attrs_by_id={})
    with (
        patch("apps.cmdb.services.instance.ModelManage.search_model_attr", return_value=[]),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.ipam_subnet.validate_subnet_no_overlap"),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        mock_graph.return_value.__enter__.return_value.query_entity.return_value = ([], 0)
        with pytest.raises(BaseAppException, match="请求参数非法") as exc_info:
            InstanceManage.instance_batch_create(
                "subnet",
                [
                    {"subnet_address": "10.0.0.0", "subnet_mask": 24},
                    {"subnet_address": "10.0.0.128", "subnet_mask": 25},
                ],
                "api-user",
                [7],
            )

    assert getattr(exc_info.value, "index", None) == 1
    mock_graph.return_value.__enter__.return_value.batch_create_entity.assert_not_called()


@pytest.mark.parametrize(
    ("attrs", "unique_rules", "instances", "update_data", "expected_field"),
    [
        (
            [{"attr_id": "serial", "attr_name": "序列号", "is_only": True, "editable": True}],
            [],
            [
                {"_id": 1, "model_id": "host", "inst_name": "h1", "serial": "s1"},
                {"_id": 2, "model_id": "host", "inst_name": "h2", "serial": "s2"},
            ],
            {"serial": "same"},
            "serial",
        ),
        (
            [
                {"attr_id": "region", "attr_name": "区域", "editable": True},
                {"attr_id": "code", "attr_name": "编码", "editable": True},
            ],
            [ModelUniqueRule(rule_id="region-code", order=1, field_ids=["region", "code"])],
            [
                {"_id": 1, "model_id": "host", "inst_name": "h1", "region": "cn", "code": "001"},
                {"_id": 2, "model_id": "host", "inst_name": "h2", "region": "us", "code": "001"},
            ],
            {"region": "cn"},
            "region",
        ),
    ],
)
def test_batch_update_rejects_merged_unique_conflict_before_graph_write(
    attrs,
    unique_rules,
    instances,
    update_data,
    expected_field,
):
    context = SimpleNamespace(
        unique_rules=unique_rules,
        attrs_by_id={item["attr_id"]: item for item in attrs},
    )
    with (
        patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_ids", return_value=instances),
        patch("apps.cmdb.services.instance.InstanceManage.check_instances_permission"),
        patch(
            "apps.cmdb.services.instance.ModelManage.search_model_info",
            return_value={"model_id": "host", "model_name": "主机", "attrs": "[]"},
        ),
        patch("apps.cmdb.services.instance.ModelManage.parse_attrs", return_value=attrs),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension", return_value=_NoopExtension()),
        patch("apps.cmdb.services.instance.batch_create_change_record"),
        patch("apps.cmdb.services.instance.schedule_instance_auto_relation_reconcile"),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        graph = mock_graph.return_value.__enter__.return_value
        graph.query_entity.return_value = (instances, len(instances))
        graph.set_entity_properties.return_value = [
            {**instance, **update_data} for instance in instances
        ]
        with pytest.raises(BaseAppException) as exc_info:
            InstanceManage.batch_instance_update([], [], [1, 2], update_data, "api-user")

    assert getattr(exc_info.value, "reason", None) == "unique_conflict"
    assert getattr(exc_info.value, "inst_id", None) == 2
    assert getattr(exc_info.value, "field", None) == expected_field
    graph.set_entity_properties.assert_not_called()


def test_batch_update_rejects_missing_query_result_before_graph_write():
    instances = [{"_id": 1, "model_id": "host", "inst_name": "h1"}]
    attrs = [{"attr_id": "status", "attr_name": "状态", "editable": True}]
    context = SimpleNamespace(unique_rules=[], attrs_by_id={"status": attrs[0]})
    with (
        patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_ids", return_value=instances),
        patch("apps.cmdb.services.instance.InstanceManage.check_instances_permission"),
        patch(
            "apps.cmdb.services.instance.ModelManage.search_model_info",
            return_value={"model_id": "host", "model_name": "主机", "attrs": "[]"},
        ),
        patch("apps.cmdb.services.instance.ModelManage.parse_attrs", return_value=attrs),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension", return_value=_NoopExtension()),
        patch("apps.cmdb.services.instance.batch_create_change_record"),
        patch("apps.cmdb.services.instance.schedule_instance_auto_relation_reconcile"),
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        graph = mock_graph.return_value.__enter__.return_value
        graph.query_entity.return_value = (instances, len(instances))
        graph.set_entity_properties.return_value = [
            {**instances[0], "status": "active"}
        ]
        with pytest.raises(BaseAppException) as exc_info:
            InstanceManage.batch_instance_update([], [], [1, 1, 2], {"status": "active"}, "api-user")

    assert getattr(exc_info.value, "reason", None) == "not_found"
    assert getattr(exc_info.value, "inst_id", None) == 2
    mock_graph.return_value.__enter__.return_value.set_entity_properties.assert_not_called()


def test_batch_delete_rejects_missing_query_result_before_audit_or_graph_write():
    instances = [{"_id": 1, "model_id": "host", "inst_name": "h1"}]
    with (
        patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_ids", return_value=instances),
        patch("apps.cmdb.services.instance.InstanceManage.check_instances_permission"),
        patch(
            "apps.cmdb.services.instance.ModelManage.search_model_info",
            return_value={"model_id": "host", "model_name": "主机"},
        ),
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension", return_value=_NoopExtension()),
        patch("apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids"),
        patch("apps.cmdb.services.instance.batch_create_change_record") as mock_audit,
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        with pytest.raises(BaseAppException) as exc_info:
            InstanceManage.instance_batch_delete([], [], [1, 1, 2], "api-user")

    assert getattr(exc_info.value, "reason", None) == "not_found"
    assert getattr(exc_info.value, "inst_id", None) == 2
    mock_audit.assert_not_called()
    mock_graph.return_value.__enter__.return_value.batch_delete_entity.assert_not_called()


@pytest.mark.parametrize(
    ("returned_instances", "expected_inst_id"),
    [
        (
            [
                {"_id": 1, "model_id": "host", "inst_name": "h1"},
                {"_id": 2, "model_id": "host", "inst_name": "h2"},
                {"_id": 2, "model_id": "host", "inst_name": "h2"},
            ],
            2,
        ),
        (
            [
                {"_id": 1, "model_id": "host", "inst_name": "h1"},
                {"_id": 2, "model_id": "host", "inst_name": "h2"},
                {"_id": 3, "model_id": "host", "inst_name": "unexpected"},
            ],
            3,
        ),
    ],
)
def test_update_and_delete_requery_reports_duplicate_or_extra_inst_id(
    returned_instances,
    expected_inst_id,
):
    with pytest.raises(BaseAppException) as exc_info:
        _require_complete_batch_instances([1, 2], returned_instances)

    assert getattr(exc_info.value, "reason", None) == "incomplete"
    assert getattr(exc_info.value, "inst_id", None) == expected_inst_id


@pytest.mark.parametrize(
    ("graph_result", "expected_inst_id"),
    [
        ([{"_id": 1, "model_id": "host", "inst_name": "h1", "status": "active"}], 2),
        (
            [
                {"_id": 1, "model_id": "host", "inst_name": "h1", "status": "active"},
                {"_id": 2, "model_id": "host", "inst_name": "h2", "status": "active"},
                {"_id": 2, "model_id": "host", "inst_name": "h2", "status": "active"},
            ],
            2,
        ),
        (
            [
                {"_id": 1, "model_id": "host", "inst_name": "h1", "status": "active"},
                {"_id": 2, "model_id": "host", "inst_name": "h2", "status": "active"},
                {"_id": 3, "model_id": "host", "inst_name": "unexpected", "status": "active"},
            ],
            3,
        ),
    ],
)
def test_batch_update_reports_incomplete_graph_result_inst_id_before_side_effects(
    graph_result,
    expected_inst_id,
):
    instances = [
        {"_id": 1, "model_id": "host", "inst_name": "h1"},
        {"_id": 2, "model_id": "host", "inst_name": "h2"},
    ]
    attrs = [{"attr_id": "status", "attr_name": "状态", "editable": True}]
    context = SimpleNamespace(unique_rules=[], attrs_by_id={"status": attrs[0]})
    with (
        patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_ids", return_value=instances),
        patch("apps.cmdb.services.instance.InstanceManage.check_instances_permission"),
        patch(
            "apps.cmdb.services.instance.ModelManage.search_model_info",
            return_value={"model_id": "host", "model_name": "主机", "attrs": "[]"},
        ),
        patch("apps.cmdb.services.instance.ModelManage.parse_attrs", return_value=attrs),
        patch("apps.cmdb.services.instance.build_unique_rule_context", return_value=context),
        patch("apps.cmdb.services.instance.get_instance_enterprise_extension", return_value=_NoopExtension()),
        patch("apps.cmdb.services.instance.batch_create_change_record") as mock_audit,
        patch("apps.cmdb.services.instance.schedule_instance_auto_relation_reconcile") as mock_schedule,
        patch("apps.cmdb.services.instance.GraphClient") as mock_graph,
    ):
        graph = mock_graph.return_value.__enter__.return_value
        graph.query_entity.return_value = (instances, len(instances))
        graph.set_entity_properties.return_value = graph_result
        with pytest.raises(BaseAppException) as exc_info:
            InstanceManage.batch_instance_update([], [], [1, 2], {"status": "active"}, "api-user")

    assert getattr(exc_info.value, "reason", None) == "incomplete"
    assert getattr(exc_info.value, "inst_id", None) == expected_inst_id
    mock_audit.assert_not_called()
    mock_schedule.assert_not_called()


@patch("apps.cmdb.services.instance.schedule_instance_auto_relation_reconcile")
@patch("apps.cmdb.services.instance.batch_create_change_record")
@patch("apps.cmdb.services.instance.GraphClient")
@patch("apps.cmdb.services.instance.ModelManage.search_model_attr")
@patch("apps.cmdb.services.instance.build_unique_rule_context")
def test_batch_create_writes_side_effects_after_all_graph_rows_succeed(
    mock_unique_rules,
    mock_attrs,
    mock_graph,
    mock_audit,
    mock_schedule,
):
    mock_unique_rules.return_value.unique_rules = []
    mock_unique_rules.return_value.attrs_by_id = {}
    mock_attrs.return_value = []
    graph = mock_graph.return_value.__enter__.return_value
    graph.query_entity.return_value = ([], 0)
    graph.batch_create_entity.return_value = [
        {
            "success": True,
            "data": {"_id": 1, "model_id": "host", "inst_name": "h1"},
        },
        {
            "success": True,
            "data": {"_id": 2, "model_id": "host", "inst_name": "h2"},
        },
    ]

    result = InstanceManage.instance_batch_create(
        "host",
        [{"inst_name": "h1"}, {"inst_name": "h2"}],
        "api-user",
        [7],
    )

    assert [item["_id"] for item in result] == [1, 2]
    mock_audit.assert_called_once()
    mock_schedule.assert_called_once_with([1, 2])
