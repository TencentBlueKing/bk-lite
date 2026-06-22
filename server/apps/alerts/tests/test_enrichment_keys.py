from apps.alerts.enrichment.keys import build_binding_key, resolve_binding


def test_build_binding_key_is_order_independent_and_hashable():
    k1 = build_binding_key({"model_id": "host", "_id": "1"})
    k2 = build_binding_key({"_id": "1", "model_id": "host"})
    assert k1 == k2
    assert hash(k1) == hash(k2)
    assert dict(k1) == {"model_id": "host", "_id": "1"}


def test_resolve_binding_maps_event_fields_to_params():
    event = {"resource_type": "host", "resource_id": "1", "resource_name": "h1"}
    binding = {"model_id": "resource_type", "_id": "resource_id"}
    assert resolve_binding(event, binding) == {"model_id": "host", "_id": "1"}


def test_resolve_binding_returns_none_when_required_field_missing():
    event = {"resource_type": "host"}  # 缺 resource_id
    binding = {"model_id": "resource_type", "_id": "resource_id"}
    assert resolve_binding(event, binding) is None
