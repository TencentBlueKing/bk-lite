"""initialize_all 必须把查询失败和实例更新失败记为失败，并继续处理其余数据。"""

TRACEBACK_TEXT = "Traceback (most recent call last):"


def _bind(monkeypatch, models, attrs):
    from apps.cmdb.display_field.initializer import DisplayFieldInitializer

    init = DisplayFieldInitializer()
    monkeypatch.setattr(init, "_get_all_models", lambda: models)
    monkeypatch.setattr(init, "_preload_mappings", lambda _models: None)
    monkeypatch.setattr(init, "_add_display_fields_to_model", lambda _model: attrs)
    return init


def test_query_failure_marks_model_failed_and_continues(monkeypatch, fake_graph):
    queried = []

    def query_entity(label, params, **kwargs):
        model_id = params[0]["value"]
        queried.append(model_id)
        if model_id == "broken-model":
            raise RuntimeError(f"graph down\n{TRACEBACK_TEXT}\n  File 'initializer.py'")
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


def test_instance_update_failure_records_one_summary(monkeypatch, fake_graph):
    model_id = "host-model"
    writes = []

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

    def set_entity_properties(label, ids, props, *args, **kwargs):
        writes.append(ids[0])
        if ids[0] == "id-fail":
            raise RuntimeError(f"write exploded\n{TRACEBACK_TEXT}\n  boom")
        return {"ok": True}

    fake_graph(
        "apps.cmdb.display_field.initializer",
        query_entity=query_entity,
        set_entity_properties=set_entity_properties,
    )
    init = _bind(
        monkeypatch,
        [{"model_id": model_id}],
        [{"attr_id": "owner", "attr_type": "user"}],
    )

    result = init.initialize_all()

    assert writes == ["id-fail", "id-ok"]
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
