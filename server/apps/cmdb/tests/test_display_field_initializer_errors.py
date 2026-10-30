"""initialize_all 必须把查询失败和实例更新失败记为失败，并继续处理其余数据。"""

import logging

TRACEBACK_TEXT = "Traceback (most recent call last):"
SENTINEL = "display-backfill-secret-sentinel"


def _bind(monkeypatch, models, attrs):
    from apps.cmdb.display_field.initializer import DisplayFieldInitializer

    init = DisplayFieldInitializer()
    monkeypatch.setattr(init, "_get_all_models", lambda: models)
    monkeypatch.setattr(init, "_preload_mappings", lambda _models: None)
    monkeypatch.setattr(init, "_add_display_fields_to_model", lambda _model: attrs)
    return init


def test_query_failure_marks_model_failed_and_continues(monkeypatch, fake_graph, caplog):
    queried = []

    def query_entity(label, params, **kwargs):
        model_id = params[0]["value"]
        queried.append(model_id)
        if model_id == "broken-model":
            secret = f"graph down\n{TRACEBACK_TEXT}\n{SENTINEL}"
            raise RuntimeError(secret)
        return ([], 0)

    def set_entity_properties(*args, **kwargs):
        raise AssertionError("查询失败或空实例不应写入")

    fake_graph(
        "apps.cmdb.display_field.initializer",
        query_entity=query_entity,
        set_entity_properties=set_entity_properties,
    )
    init = _bind(
        monkeypatch,
        [{"model_id": "broken-model"}, {"model_id": "empty-model"}],
        [{"attr_id": "owner", "attr_type": "user"}],
    )

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        result = init.initialize_all()

    assert queried == ["broken-model", "empty-model"]
    assert result["success"] is False
    assert result["models_processed"] == 1
    assert result["instances_processed"] == 0
    assert len(result["errors"]) == 1
    error = result["errors"][0]
    assert "broken-model" in error
    assert "查询实例" in error
    assert "empty-model" not in error
    assert TRACEBACK_TEXT not in error
    records = [record for record in caplog.records if record.getMessage().startswith("[DisplayFieldInitializer] event=display_backfill_query_failed")]
    assert len(records) == 1
    assert records[0].getMessage() == (
        "[DisplayFieldInitializer] event=display_backfill_query_failed model_id=broken-model failed_stage=query_instance error_type=RuntimeError"
    )
    assert SENTINEL not in records[0].getMessage()
    assert records[0].exc_info[0].__name__ == "SafeLogException"
    assert str(records[0].exc_info[1]) == "RuntimeError"
    formatted = logging.Formatter().format(records[0])
    assert SENTINEL not in formatted
    assert "SafeLogException: RuntimeError" in formatted


def test_instance_update_failure_records_one_summary(monkeypatch, fake_graph, caplog):
    model_id = "host-model"
    written = []

    def query_entity(label, params, **kwargs):
        assert params[0]["value"] == model_id
        return (
            [
                {"_id": "id-fail", "inst_id": "inst-fail", "owner": [7]},
                {"_id": "id-plain", "inst_id": "inst-plain", "name": "no-display"},
                {"_id": "id-ok", "inst_id": "inst-ok", "owner": [8]},
            ],
            3,
        )

    def batch_update_node_property_values(label, field, property_values):
        if any(item["id"] == "id-fail" for item in property_values):
            secret = f"write exploded\n{TRACEBACK_TEXT}\n{SENTINEL}"
            raise RuntimeError(secret)
        written.extend(item["id"] for item in property_values)
        return []

    fake_graph(
        "apps.cmdb.display_field.initializer",
        query_entity=query_entity,
        batch_update_node_property_values=batch_update_node_property_values,
    )
    init = _bind(
        monkeypatch,
        [{"model_id": model_id}],
        [{"attr_id": "owner", "attr_type": "user"}],
    )

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        result = init.initialize_all()

    assert written == ["id-ok"]
    assert result["success"] is False
    assert result["instances_processed"] == 1
    assert result["models_processed"] == 0
    assert len(result["errors"]) == 1
    error = result["errors"][0]
    assert model_id in error
    assert "inst-fail" in error
    assert "失败1次" in error
    assert "inst-plain" not in error
    assert "inst-ok" not in error
    assert TRACEBACK_TEXT not in error
    records = [record for record in caplog.records if record.getMessage().startswith("[DisplayFieldInitializer] event=display_backfill_write_failed")]
    assert len(records) == 1
    message = records[0].getMessage()
    assert message == (
        "[DisplayFieldInitializer] event=display_backfill_write_failed model_id=host-model "
        "failed_stage=write_instance error_type=RuntimeError failure_count=1"
    )
    assert SENTINEL not in message
    assert records[0].exc_info[0].__name__ == "SafeLogException"
    assert str(records[0].exc_info[1]) == "RuntimeError"
    formatted = logging.Formatter().format(records[0])
    assert SENTINEL not in formatted
    assert "SafeLogException: RuntimeError" in formatted


def test_unchanged_display_value_is_not_written(monkeypatch, fake_graph):
    def query_entity(label, params, **kwargs):
        return ([{"_id": 1, "inst_id": "inst-1", "owner": [7], "owner_display": "7"}], 1)

    def batch_update_node_property_values(*args, **kwargs):
        raise AssertionError("未变化的 _display 不应写图")

    fake_graph(
        "apps.cmdb.display_field.initializer",
        query_entity=query_entity,
        batch_update_node_property_values=batch_update_node_property_values,
    )
    init = _bind(
        monkeypatch,
        [{"model_id": "host"}],
        [{"attr_id": "owner", "attr_type": "user"}],
    )

    result = init.initialize_all()

    assert result["success"] is True
    assert result["instances_processed"] == 0
    assert result["errors"] == []


def test_instance_pages_advance_cursor(monkeypatch, fake_graph):
    from apps.cmdb.display_field.initializer import DisplayFieldInitializer

    monkeypatch.setattr(DisplayFieldInitializer, "INSTANCE_PAGE_SIZE", 2)
    pages = [
        [
            {"_id": 1, "inst_id": "a", "owner": [1]},
            {"_id": 2, "inst_id": "b", "owner": [1]},
        ],
        [{"_id": 3, "inst_id": "c", "owner": [1]}],
    ]
    seen_params = []

    def query_entity(label, params, **kwargs):
        seen_params.append(list(params))
        assert kwargs["page"]["limit"] == 2
        assert kwargs["include_count"] is False
        return (pages.pop(0), 0)

    fake_graph(
        "apps.cmdb.display_field.initializer",
        query_entity=query_entity,
        batch_update_node_property_values=lambda *args, **kwargs: [],
    )
    init = _bind(
        monkeypatch,
        [{"model_id": "host"}],
        [{"attr_id": "owner", "attr_type": "user"}],
    )
    init._user_map = {1: {"username": "admin", "display_name": "管理员"}}

    result = init.initialize_all()

    assert result["success"] is True
    assert result["instances_processed"] == 3
    assert len(seen_params) == 2
    assert seen_params[0] == [{"field": "model_id", "type": "str=", "value": "host"}]
    assert seen_params[1][1] == {"field": "id", "type": "id>", "value": 2}
