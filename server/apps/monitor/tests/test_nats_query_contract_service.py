"""监控 NATS 查询接缝拆分契约。"""

import importlib

from nats_client.registry import default_registry


def test_query_contract_service_has_no_registration_side_effects():
    before = set(default_registry.registry)

    service = importlib.import_module("apps.monitor.services.nats_query_contract")
    importlib.reload(service)

    assert set(default_registry.registry) == before


def test_legacy_monitor_module_reexports_query_contract_helpers():
    from apps.monitor.nats import monitor
    from apps.monitor.services import nats_query_contract

    assert monitor._normalize_monitor_query_data({"monitor_object_id": 1}) == nats_query_contract.normalize_monitor_query_data(
        {"monitor_object_id": 1}
    )
    assert monitor._normalize_positive_int("2", "page") == nats_query_contract.normalize_positive_int("2", "page")
    assert monitor._normalize_bool("true", "enabled") == nats_query_contract.normalize_bool("true", "enabled")
    assert monitor._normalize_filter_values("a,b", "filters") == nats_query_contract.normalize_filter_values("a,b", "filters")
    assert monitor._build_vm_query_failure_result({}, "failed") == nats_query_contract.build_vm_query_failure_result({}, "failed")
    assert monitor._paginate_items([1, 2], 1, 1) == nats_query_contract.paginate_items([1, 2], 1, 1)


def test_query_contract_service_preserves_representative_behavior():
    from apps.monitor.services import nats_query_contract as service

    assert service.normalize_monitor_query_data({"monitor_object_id": 7, "start_time": 10, "end_time": 20}) == {
        "monitor_object_id": 7,
        "monitor_obj_id": 7,
        "start_time": 10,
        "start": 10,
        "end_time": 20,
        "end": 20,
    }
    assert service.normalize_positive_int("3", "page") == 3
    assert service.normalize_bool("yes", "enabled") is True
    assert service.normalize_filter_values("a, b", "filters") == ["a", "b"]
    assert service.build_vm_query_failure_result({"error": "invalid", "errorType": "bad_data"}, "query failed") == {
        "result": False,
        "data": [],
        "message": "bad_data: invalid",
    }
    assert service.paginate_items([1, 2, 3], 2, 2) == {
        "count": 3,
        "page": 2,
        "page_size": 2,
        "items": [3],
    }
